/* ==========================================================================
 *  MARCO 2 - PRODUTOR
 *  Software para Sistemas Ubiquos - UFG / INF
 *
 *  Grupo ......: Felipe Alves, Felipe O Carvalho, Matheus Augusto, Murilo
 *  Projeto ....: monitoramento de sinais vitais por smart clothing
 *  Derivado de : prototipo do Marco 1 (estado e processamento temporal)
 *
 *  FRONTEIRA INTEGRADA
 *  produtor (ESP32/Wokwi) --MQTT--> consumidor (servico Python)
 *
 *  O que este componente faz alem do Marco 1:
 *    - conecta a WiFi e a um broker MQTT;
 *    - publica o evento de mudanca de estado no topico de state;
 *    - mantem FILA LOCAL quando o broker esta indisponivel e reenvia em
 *      ordem na reconexao (condicao de falha exercitada);
 *    - declara LAST WILL: o broker anuncia "offline" se a conexao cair sem
 *      encerramento, tornando o silencio do dispositivo observavel.
 *
 *  O potenciometro e ENTRADA SUBSTITUTA: nao ha aquisicao de frequencia
 *  cardiaca real e nenhuma saida tem valor clinico.
 * ========================================================================= */

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

/* --------------------------------------------------------------------------
 *  MODO_DEMO reduz janelas e tempos para caber na apresentacao.
 *  1 = demonstracao (janela 20 s)    0 = parametros do projeto (janela 60 s)
 * ------------------------------------------------------------------------- */
#define MODO_DEMO 1

#if MODO_DEMO
  #define JANELA_FC_S           20
  #define JANELA_MOV_S          10
  #define PASSO_AVALIACAO_MS    5000
  #define TEMPO_MINIMO_ESTADO_MS 10000
#else
  #define JANELA_FC_S           60
  #define JANELA_MOV_S          30
  #define PASSO_AVALIACAO_MS    15000
  #define TEMPO_MINIMO_ESTADO_MS 30000
#endif


/* == 1. CONFIGURACAO ===================================================== */

const char* WIFI_SSID  = "Wokwi-GUEST";
const char* WIFI_PASS  = "";

const char* MQTT_HOST  = "broker.hivemq.com";   // broker publico
const uint16_t MQTT_PORT = 1883;

// ATENCAO: prefixo unico do grupo. Broker publico e compartilhado -
// sem prefixo proprio o consumidor pode receber publicacoes de terceiros.
const char* TOPICO_BASE   = "ufg/ssu/2026-2/internet-das-coisos/patient-0042";
const char* TOPICO_STATE  = "ufg/ssu/2026-2/internet-das-coisos/patient-0042/state";
const char* TOPICO_STATUS = "ufg/ssu/2026-2/internet-das-coisos/patient-0042/status";

const char* DEVICE_ID     = "esp32-borda-01";
const char* ENTITY_ID     = "patient-0042";
const int   SCHEMA_VERSION = 1;

const uint8_t PINO_FC     = 34;
const uint8_t PINO_BOTAO  = 15;
const uint8_t PINO_LED_R  = 25;
const uint8_t PINO_LED_G  = 26;
const uint8_t PINO_LED_B  = 27;
const uint8_t PINO_BUZZER = 4;

const uint32_t PERIODO_AMOSTRAGEM_MS = 1000;
const uint32_t RETENTATIVA_MQTT_MS   = 3000;

// O Wokwi roda mais devagar que o tempo real com WiFi ativo: 15 s de millis()
// podem levar mais de 22 s reais. Com o keepalive padrao do PubSubClient
// (15 s) o PING chega atrasado, o broker derruba a conexao e publica o last
// will sem que nada tenha falhado. Por isso o produtor declara ao broker uma
// tolerancia maior do que o intervalo em que de fato pinga.
const uint16_t MQTT_KEEPALIVE_BROKER_S  = 40;  // broker espera ate 1,5x = 60 s
const uint16_t MQTT_KEEPALIVE_CLIENTE_S = 10;  // cliente pinga a cada 10 s simulados

const float FC_MIN_VALIDA = 30.0;
const float FC_MAX_VALIDA = 220.0;
const float FC_ESCALA_MAX = 250.0;

const float GRAVIDADE         = 9.80665;
const float G_REST_TOLERANCIA = 0.15;
const float G_MAX_PLAUSIVEL   = 8.0;

const float COBERTURA_MINIMA  = 0.70;
const float FC_LIMIAR_ENTRADA = 100.0;
const float FC_LIMIAR_SAIDA   = 92.0;
const uint8_t AVALIACOES_PARA_ENTRAR = 2;

const uint8_t FILA_TAMANHO = 12;   // eventos guardados durante a desconexao


/* == 2. TIPOS ============================================================ */

enum QualidadeLeitura { LEITURA_OK, LEITURA_FORA_DE_FAIXA, LEITURA_AUSENTE };
enum EstadoMovimento  { MOV_REST, MOV_ACTIVE, MOV_INVALIDO };
enum Estado { EST_DESCONHECIDO, EST_DADOS_INSUFICIENTES, EST_NORMAL, EST_ATENCAO };


/* == 3. ESTADO GLOBAL ==================================================== */

WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
Adafruit_MPU6050 mpu;
bool mpuPresente = false;

float   fcAmostras[JANELA_FC_S];
bool    fcValida[JANELA_FC_S];
uint8_t fcIndice = 0;
uint8_t movAmostras[JANELA_MOV_S];
uint8_t movIndice = 0;

uint32_t proximaAmostraMs   = 0;
uint32_t proximaAvaliacaoMs = 0;
uint32_t proximaTentativaMs = 0;
uint32_t totalAmostras      = 0;
uint32_t sequenceEvento     = 0;

Estado   estadoAtual        = EST_DESCONHECIDO;
uint32_t entrouNoEstadoMs   = 0;
uint8_t  avaliacoesCondicao = 0;
bool     alertaAtivo        = false;

// Fila local: preserva eventos produzidos enquanto o broker esta ausente.
char     fila[FILA_TAMANHO][320];
uint8_t  filaInicio = 0, filaFim = 0, filaCheia = 0;

// Falha simulada: 'f' no monitor serial derruba a conexao e impede a
// reconexao ate o proximo 'f'. Serve para exercitar a fila na demonstracao.
bool     falhaSimulada = false;


/* == 4. ENTRADA E VALIDACAO ============================================== */

QualidadeLeitura lerFrequenciaCardiaca(float &bpm) {
  if (digitalRead(PINO_BOTAO) == LOW) { bpm = NAN; return LEITURA_AUSENTE; }
  bpm = (analogRead(PINO_FC) / 4095.0) * FC_ESCALA_MAX;
  if (bpm < FC_MIN_VALIDA || bpm > FC_MAX_VALIDA) return LEITURA_FORA_DE_FAIXA;
  return LEITURA_OK;
}

EstadoMovimento lerMovimento(float &magnitudeG) {
  if (!mpuPresente || digitalRead(PINO_BOTAO) == LOW) {
    magnitudeG = NAN; return MOV_INVALIDO;
  }
  sensors_event_t a, gyro, temp;
  if (!mpu.getEvent(&a, &gyro, &temp)) { magnitudeG = NAN; return MOV_INVALIDO; }

  float mag = sqrt(a.acceleration.x * a.acceleration.x +
                   a.acceleration.y * a.acceleration.y +
                   a.acceleration.z * a.acceleration.z) / GRAVIDADE;
  magnitudeG = mag;
  if (mag > G_MAX_PLAUSIVEL) return MOV_INVALIDO;
  if (fabs(mag - 1.0) <= G_REST_TOLERANCIA) return MOV_REST;
  return MOV_ACTIVE;
}


/* == 5. JANELA E COBERTURA =============================================== */

void limparJanelas() {
  for (uint8_t i = 0; i < JANELA_FC_S; i++)  fcValida[i] = false;
  for (uint8_t i = 0; i < JANELA_MOV_S; i++) movAmostras[i] = MOV_INVALIDO;
}

void gravarAmostra(float bpm, QualidadeLeitura q, EstadoMovimento mov) {
  fcAmostras[fcIndice] = bpm;
  fcValida[fcIndice]   = (q == LEITURA_OK);
  fcIndice = (fcIndice + 1) % JANELA_FC_S;
  movAmostras[movIndice] = mov;
  movIndice = (movIndice + 1) % JANELA_MOV_S;
}

float coberturaFc() {
  uint8_t v = 0;
  for (uint8_t i = 0; i < JANELA_FC_S; i++) if (fcValida[i]) v++;
  return (float)v / JANELA_FC_S;
}

float coberturaMov() {
  uint8_t v = 0;
  for (uint8_t i = 0; i < JANELA_MOV_S; i++) if (movAmostras[i] != MOV_INVALIDO) v++;
  return (float)v / JANELA_MOV_S;
}

float mediaFc() {
  float soma = 0; uint8_t v = 0;
  for (uint8_t i = 0; i < JANELA_FC_S; i++) if (fcValida[i]) { soma += fcAmostras[i]; v++; }
  return v ? soma / v : NAN;
}

EstadoMovimento movimentoPredominante() {
  uint8_t rest = 0, active = 0;
  for (uint8_t i = 0; i < JANELA_MOV_S; i++) {
    if (movAmostras[i] == MOV_REST) rest++;
    else if (movAmostras[i] == MOV_ACTIVE) active++;
  }
  if (rest == 0 && active == 0) return MOV_INVALIDO;
  return (rest >= active) ? MOV_REST : MOV_ACTIVE;
}


/* == 6. NOMES ============================================================ */

const char* nomeMovimento(EstadoMovimento m) {
  switch (m) { case MOV_REST: return "REST";
               case MOV_ACTIVE: return "ACTIVE";
               default: return "INVALIDO"; }
}

const char* nomeEstado(Estado e) {
  switch (e) { case EST_NORMAL: return "NORMAL";
               case EST_ATENCAO: return "ATENCAO";
               case EST_DADOS_INSUFICIENTES: return "DADOS_INSUFICIENTES";
               default: return "DESCONHECIDO"; }
}

const char* nomeQualidade(QualidadeLeitura q) {
  switch (q) { case LEITURA_OK: return "OK";
               case LEITURA_FORA_DE_FAIXA: return "FORA_DE_FAIXA";
               default: return "AUSENTE"; }
}


/* == 7. COMUNICACAO: FILA LOCAL E PUBLICACAO ============================= */

/* A fila preserva eventos gerados enquanto o broker esta indisponivel.
 * O estado de negocio continua evoluindo mesmo sem rede; o que a desconexao
 * interrompe e a entrega, nao a decisao.                                   */
void enfileirar(const char* payload) {
  strncpy(fila[filaFim], payload, sizeof(fila[0]) - 1);
  fila[filaFim][sizeof(fila[0]) - 1] = '\0';
  filaFim = (filaFim + 1) % FILA_TAMANHO;
  if (filaCheia) filaInicio = (filaInicio + 1) % FILA_TAMANHO;  // descarta o mais antigo
  if (filaFim == filaInicio) filaCheia = 1;
}

uint8_t filaTamanho() {
  if (filaCheia) return FILA_TAMANHO;
  return (filaFim + FILA_TAMANHO - filaInicio) % FILA_TAMANHO;
}

void esvaziarFila() {
  while (filaTamanho() > 0 && mqtt.connected()) {
    if (!mqtt.publish(TOPICO_STATE, fila[filaInicio])) break;
    Serial.printf("[%lu] fila: reenviado (%u restantes)\n",
                  millis(), (unsigned)(filaTamanho() - 1));
    filaInicio = (filaInicio + 1) % FILA_TAMANHO;
    filaCheia = 0;
  }
}

void publicar(const char* payload) {
  if (mqtt.connected() && mqtt.publish(TOPICO_STATE, payload)) {
    Serial.printf("[%lu] mqtt: publicado em %s\n", millis(), TOPICO_STATE);
  } else {
    enfileirar(payload);
    Serial.printf("[%lu] mqtt: INDISPONIVEL - evento enfileirado (%u na fila)\n",
                  millis(), filaTamanho());
  }
}

void lerComandoSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c != 'f' && c != 'F') continue;
    falhaSimulada = !falhaSimulada;
    if (falhaSimulada) {
      mqtt.disconnect();
      Serial.printf("[%lu] FALHA SIMULADA: broker indisponivel (tecle f para restaurar)\n", millis());
    } else {
      Serial.printf("[%lu] falha simulada encerrada - reconectando\n", millis());
    }
  }
}

void conectarMqtt() {
  if (falhaSimulada) return;
  if (WiFi.status() != WL_CONNECTED) return;
  if ((int32_t)(millis() - proximaTentativaMs) < 0) return;
  proximaTentativaMs = millis() + RETENTATIVA_MQTT_MS;

  char clientId[48];
  snprintf(clientId, sizeof(clientId), "%s-%04X", DEVICE_ID, (uint16_t)random(0xFFFF));

  Serial.printf("[%lu] mqtt: conectando a %s...\n", millis(), MQTT_HOST);

  /* Last will: se a conexao cair sem encerramento, o proprio broker publica
   * "offline" no topico de status. O silencio do dispositivo passa a ser
   * observavel pelo consumidor.                                            */
  mqtt.setKeepAlive(MQTT_KEEPALIVE_BROKER_S);     // valor enviado no CONNECT
  bool ok = mqtt.connect(clientId, NULL, NULL,
                         TOPICO_STATUS, 1, true, "{\"status\":\"offline\"}");
  mqtt.setKeepAlive(MQTT_KEEPALIVE_CLIENTE_S);    // intervalo real de PING
  if (ok) {
    Serial.printf("[%lu] mqtt: conectado\n", millis());
    mqtt.publish(TOPICO_STATUS, "{\"status\":\"online\"}", true);
    esvaziarFila();
  } else {
    Serial.printf("[%lu] mqtt: falhou (rc=%d)\n", millis(), mqtt.state());
  }
}


/* == 8. EVENTO =========================================================== */

void emitirEvento(const char* tipo, uint32_t agora, const char* razao,
                  float fcMedia, EstadoMovimento mov, float cobFc, float cobMov) {
  sequenceEvento++;

  char valor[16];
  if (isnan(fcMedia)) strcpy(valor, "null");
  else                snprintf(valor, sizeof(valor), "%.1f", fcMedia);

  char payload[320];
  snprintf(payload, sizeof(payload),
    "{\"schemaVersion\":%d,\"eventType\":\"%s\",\"eventId\":\"%s-%lu\","
    "\"deviceId\":\"%s\",\"entityId\":\"%s\",\"eventTimeMs\":%lu,\"sequence\":%lu,"
    "\"value\":%s,\"unit\":\"bpm\",\"state\":\"%s\",\"motion\":\"%s\","
    "\"coverageFc\":%.2f,\"coverageMov\":%.2f,\"reason\":\"%s\"}",
    SCHEMA_VERSION, tipo, DEVICE_ID, sequenceEvento,
    DEVICE_ID, ENTITY_ID, agora, sequenceEvento,
    valor, nomeEstado(estadoAtual), nomeMovimento(mov), cobFc, cobMov, razao);

  Serial.println(payload);
  publicar(payload);
}


/* == 9. ESTADO E REGRA =================================================== */

void atualizarAtuacao();

bool podeTransitar(Estado destino, uint32_t agora) {
  if (destino == EST_DADOS_INSUFICIENTES) return true;
  return (agora - entrouNoEstadoMs) >= TEMPO_MINIMO_ESTADO_MS;
}

void transitarPara(Estado novo, const char* razao, uint32_t agora,
                   float fcMedia, EstadoMovimento mov, float cobFc, float cobMov) {
  if (novo == estadoAtual) return;

  Serial.printf("[%lu] estado %s -> %s (%s)\n", agora,
                nomeEstado(estadoAtual), nomeEstado(novo), razao);

  estadoAtual      = novo;
  entrouNoEstadoMs = agora;
  if (novo == EST_ATENCAO) alertaAtivo = true;
  if (novo == EST_NORMAL)  alertaAtivo = false;

  atualizarAtuacao();
  emitirEvento("vitals.state.changed", agora, razao, fcMedia, mov, cobFc, cobMov);
}

void avaliarRegra(uint32_t agora, float fcMedia, EstadoMovimento mov,
                  float cobFc, float cobMov) {
  bool janelaValida = (cobFc >= COBERTURA_MINIMA) && (cobMov >= COBERTURA_MINIMA);

  if (!janelaValida) {
    avaliacoesCondicao = 0;
    transitarPara(EST_DADOS_INSUFICIENTES, "cobertura_insuficiente",
                  agora, fcMedia, mov, cobFc, cobMov);
    return;
  }

  if (estadoAtual == EST_ATENCAO) {
    bool mantida = (fcMedia > FC_LIMIAR_SAIDA) && (mov == MOV_REST);
    if (!mantida && podeTransitar(EST_NORMAL, agora)) {
      avaliacoesCondicao = 0;
      transitarPara(EST_NORMAL, "condicao_cessou", agora, fcMedia, mov, cobFc, cobMov);
    }
    return;
  }

  bool condicao = (fcMedia > FC_LIMIAR_ENTRADA) && (mov == MOV_REST);
  avaliacoesCondicao = condicao ? avaliacoesCondicao + 1 : 0;

  if (avaliacoesCondicao >= AVALIACOES_PARA_ENTRAR && podeTransitar(EST_ATENCAO, agora)) {
    transitarPara(EST_ATENCAO, "condicao_persistiu", agora, fcMedia, mov, cobFc, cobMov);
  } else if (estadoAtual != EST_NORMAL) {
    transitarPara(EST_NORMAL, "janela_com_cobertura", agora, fcMedia, mov, cobFc, cobMov);
  }
}


/* == 10. ATUACAO ========================================================= */

void escreverLed(bool r, bool g, bool b) {
  digitalWrite(PINO_LED_R, r ? HIGH : LOW);
  digitalWrite(PINO_LED_G, g ? HIGH : LOW);
  digitalWrite(PINO_LED_B, b ? HIGH : LOW);
}

void atualizarAtuacao() {
  switch (estadoAtual) {
    case EST_NORMAL:  escreverLed(false, true,  false); break;
    case EST_ATENCAO: escreverLed(true,  false, false); break;
    default:          escreverLed(false, false, true);  break;
  }
  digitalWrite(PINO_BUZZER, alertaAtivo ? HIGH : LOW);
}


/* == 11. SETUP =========================================================== */

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(PINO_BOTAO, INPUT_PULLUP);
  pinMode(PINO_LED_R, OUTPUT); pinMode(PINO_LED_G, OUTPUT);
  pinMode(PINO_LED_B, OUTPUT); pinMode(PINO_BUZZER, OUTPUT);

  limparJanelas();
  atualizarAtuacao();

  Serial.println();
  Serial.println("=== MARCO 2 | PRODUTOR | ESP32 -> MQTT ===");
  Serial.printf("topico state : %s\n", TOPICO_STATE);
  Serial.printf("topico status: %s\n", TOPICO_STATUS);
  Serial.printf("janelas: FC %ds, MOV %ds | passo %ds | modo demo: %s\n",
                JANELA_FC_S, JANELA_MOV_S, PASSO_AVALIACAO_MS / 1000,
                MODO_DEMO ? "SIM" : "NAO");

  Wire.begin();
  mpuPresente = mpu.begin();
  if (mpuPresente) {
    mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }
  Serial.println(mpuPresente ? "[setup] MPU6050 inicializado"
                             : "[setup] MPU6050 ausente");

  Serial.printf("[setup] WiFi: conectando a %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);          // canal 6 acelera no Wokwi
  while (WiFi.status() != WL_CONNECTED) { delay(200); Serial.print("."); }
  Serial.printf("\n[setup] WiFi conectado, IP %s\n", WiFi.localIP().toString().c_str());

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  conectarMqtt();

  uint32_t agora = millis();
  proximaAmostraMs   = agora;
  proximaAvaliacaoMs = agora + PASSO_AVALIACAO_MS;
  entrouNoEstadoMs   = agora;
}


/* == 12. LOOP ============================================================ */

bool chegouAHora(uint32_t agora, uint32_t &proximo, uint32_t periodo) {
  if ((int32_t)(agora - proximo) < 0) return false;
  proximo += periodo;
  return true;
}

void loop() {
  uint32_t agora = millis();

  lerComandoSerial();

  // Comunicacao: reconecta sem bloquear a coleta nem a decisao.
  if (!mqtt.connected()) conectarMqtt();
  else { mqtt.loop(); if (filaTamanho() > 0) esvaziarFila(); }

  if (chegouAHora(agora, proximaAmostraMs, PERIODO_AMOSTRAGEM_MS)) {
    float bpm, magG;
    QualidadeLeitura q  = lerFrequenciaCardiaca(bpm);
    EstadoMovimento  mv = lerMovimento(magG);
    totalAmostras++;
    gravarAmostra(bpm, q, mv);

    Serial.printf("[%lu] seq=%lu fc=", agora, totalAmostras);
    if (q == LEITURA_AUSENTE) Serial.print("--"); else Serial.printf("%.1f", bpm);
    Serial.printf("bpm(%s) mov=%s\n", nomeQualidade(q), nomeMovimento(mv));
  }

  if (chegouAHora(agora, proximaAvaliacaoMs, PASSO_AVALIACAO_MS)) {
    float cobFc = coberturaFc(), cobMov = coberturaMov(), fcMedia = mediaFc();
    EstadoMovimento mov = movimentoPredominante();

    avaliarRegra(agora, fcMedia, mov, cobFc, cobMov);

    Serial.printf("[%lu] avaliacao cobFc=%.2f cobMov=%.2f fcMedia=", agora, cobFc, cobMov);
    if (isnan(fcMedia)) Serial.print("--"); else Serial.printf("%.1f", fcMedia);
    Serial.printf(" mov=%s estado=%s persistencia=%u/%u mqtt=%s fila=%u\n",
                  nomeMovimento(mov), nomeEstado(estadoAtual),
                  avaliacoesCondicao, AVALIACOES_PARA_ENTRAR,
                  mqtt.connected() ? "ON" : "OFF", filaTamanho());
  }
}
