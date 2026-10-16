/* ==========================================================================
 *  MARCO 3 - PRODUTOR (ESP32/Wokwi, Arduino C++)
 *  Projeto acadêmico: Internet dos Coisos - Software para Sistemas Ubíquos
 *
 *  Marco 1/2 preservado: sensores, janelas, cobertura, regra, LED/buzzer,
 *  fila de eventos e modo de simular falha.
 *  Evolução do Marco 3: HTTP POST + chave do dispositivo + heartbeat.
 *  Caminho GRATUITO: Wokwi (gateway publico) -> HTTPS -> tunel Cloudflare
 *  -> API no PC do grupo. O certificado do servidor e sempre validado.
 *  Atuacao reduzida a UM LED + buzzer.
 *  O potenciômetro NÃO é um sensor cardíaco real.
 * ========================================================================== */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include "config.h"            // gerado por marco3/api/gerar_config.py (NAO versionar)
#include "certificados_raiz.h" // raizes publicas usadas para validar o HTTPS

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

// API_BASE_URL e DEVICE_API_KEY estao em config.h (NAO versionar segredos).
// API_BASE_URL = endereco https://....trycloudflare.com mostrado pelo tunel.

const char* DEVICE_ID     = "esp32-borda-01";
const char* ENTITY_ID     = "patient-0042";
const int   SCHEMA_VERSION = 2;

const uint8_t PINO_FC     = 34;
const uint8_t PINO_BOTAO  = 15;   // "silenciar": leitura ausente
const uint8_t PINO_FALHA  = 13;   // "falha HTTP": alterna a falha simulada
const uint8_t PINO_LED    = 25;   // apagado=NORMAL, aceso=ATENCAO, piscando=sem dados
const uint8_t PINO_BUZZER = 4;

const uint32_t PERIODO_AMOSTRAGEM_MS = 1000;

// Um POST HTTPS (com handshake TLS) pode bloquear por ate ~5 s.
// Intervalos limitam o impacto de falhas HTTP na amostragem e na decisao local.
const uint32_t TIMEOUT_HTTP_MS = 5000;
const uint32_t RETENTATIVA_HTTP_MS = 10000;
const uint32_t ENTRE_ENVIOS_MS = 1200;
const uint32_t PISCA_LED_MS = 500;
const uint32_t HEARTBEAT_MS = 15000;
const uint32_t WIFI_RETRY_MS = 10000;

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

Adafruit_MPU6050 mpu;
bool mpuPresente = false;

float   fcAmostras[JANELA_FC_S];
bool    fcValida[JANELA_FC_S];
uint8_t fcIndice = 0;
uint8_t movAmostras[JANELA_MOV_S];
uint8_t movIndice = 0;

uint32_t proximaAmostraMs   = 0;
uint32_t proximaAvaliacaoMs = 0;
uint32_t proximaTentativaHttpMs = 0;
uint32_t proximoHeartbeatMs = 0;
uint32_t proximaWiFiMs = 0;
char     bootId[12] = {0};
uint32_t totalAmostras      = 0;
uint32_t sequenceEvento     = 0;

Estado   estadoAtual        = EST_DESCONHECIDO;
uint32_t entrouNoEstadoMs   = 0;
uint8_t  avaliacoesCondicao = 0;
bool     alertaAtivo        = false;

// Fila local: preserva eventos produzidos enquanto a API HTTP esta ausente.
char     fila[FILA_TAMANHO][440];
uint8_t  filaInicio = 0, filaFim = 0, filaCheia = 0;

// Falha simulada: botão GPIO13 ou 'f' faz POST falhar propositalmente.
// As leituras, as decisões locais e o buzzer continuam funcionando.
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


/* == 7. COMUNICACAO HTTP, FILA E HEARTBEAT =============================== */

// A fila mantem a ordem: nao envia evento novo na frente de evento antigo.
void enfileirar(const char* payload) {
  strncpy(fila[filaFim], payload, sizeof(fila[0]) - 1);
  fila[filaFim][sizeof(fila[0]) - 1] = '\0';
  filaFim = (filaFim + 1) % FILA_TAMANHO;
  if (filaCheia) filaInicio = (filaInicio + 1) % FILA_TAMANHO;
  if (filaFim == filaInicio) filaCheia = 1;
}

uint8_t filaTamanho() {
  if (filaCheia) return FILA_TAMANHO;
  return (filaFim + FILA_TAMANHO - filaInicio) % FILA_TAMANHO;
}

// Envia um HTTP POST sobre TLS (HTTPS), validando o certificado do servidor
// com as raizes de certificados_raiz.h. Nunca usa setInsecure(): se a
// validacao falhar, a conexao e recusada e o evento continua na fila.
int postJson(const char* rota, const char* payload) {
  if (falhaSimulada || WiFi.status() != WL_CONNECTED) return -1;

  String base = String(API_BASE_URL);
  if (base.endsWith("/")) base.remove(base.length() - 1);
  if (!base.startsWith("https://")) {
    Serial.println("[HTTP] API_BASE_URL deve ser o endereco https:// do tunel");
    return -1;
  }

  WiFiClientSecure cliente;
  cliente.setCACert(HTTPS_ROOT_CA);
  HTTPClient http;
  http.setConnectTimeout(TIMEOUT_HTTP_MS);
  http.setTimeout(TIMEOUT_HTTP_MS);
  if (!http.begin(cliente, base + rota)) return -1;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_API_KEY);
  int codigo = http.POST((uint8_t*)payload, strlen(payload));
  http.end();
  return codigo;
}

void enviarDaFila(uint32_t agora) {
  if (filaTamanho() == 0 || falhaSimulada ||
      (int32_t)(agora - proximaTentativaHttpMs) < 0) return;

  // Uma mensagem por tentativa: POSTs lentos nao travam o loop por minutos.
  int codigo = postJson("/api/eventos", fila[filaInicio]);
  if (codigo == 200 || codigo == 201) {
    Serial.printf("[%lu] HTTP %d: evento entregue (seq na fila, %u restantes)\n",
                  millis(), codigo, (unsigned)(filaTamanho() - 1));
    filaInicio = (filaInicio + 1) % FILA_TAMANHO;
    filaCheia = 0;
    proximaTentativaHttpMs = millis() + ENTRE_ENVIOS_MS;
  } else if (codigo == 400 || codigo == 403 || codigo == 409) {
    // Erros permanentes do evento: descarta-o para nao bloquear toda a fila.
    Serial.printf("[%lu] HTTP %d: evento rejeitado; descartando da fila\n", millis(), codigo);
    filaInicio = (filaInicio + 1) % FILA_TAMANHO;
    filaCheia = 0;
    proximaTentativaHttpMs = millis() + ENTRE_ENVIOS_MS;
  } else {
    // HTTP 401: chave invalida; manter evento para corrigir a config.
    Serial.printf("[%lu] HTTP falhou (%d); fila preservada (%u)\n",
                  millis(), codigo, filaTamanho());
    proximaTentativaHttpMs = millis() + RETENTATIVA_HTTP_MS;
  }
}

void publicar(const char* payload) {
  enfileirar(payload);
  Serial.printf("[%lu] evento armazenado para HTTP (%u na fila)\n", millis(), filaTamanho());
  enviarDaFila(millis());
}

void enviarHeartbeat(uint32_t agora) {
  if ((int32_t)(agora - proximoHeartbeatMs) < 0) return;
  proximoHeartbeatMs = agora + HEARTBEAT_MS;
  if (falhaSimulada || filaTamanho() > 0) return;
  char payload[160];
  snprintf(payload, sizeof(payload),
           "{\"deviceId\":\"%s\",\"entityId\":\"%s\",\"bootId\":\"%s\"}",
           DEVICE_ID, ENTITY_ID, bootId);
  int codigo = postJson("/api/heartbeat", payload);
  Serial.printf("[%lu] heartbeat: HTTP %d\n", millis(), codigo);
}

void alternarFalhaSimulada() {
  falhaSimulada = !falhaSimulada;
  if (falhaSimulada) {
    Serial.println("FALHA SIMULADA: HTTP indisponivel; eventos ficam na fila");
  } else {
    Serial.println("FALHA SIMULADA ENCERRADA: retomando envios HTTP");
    proximaTentativaHttpMs = 0;
    proximoHeartbeatMs = 0;
  }
}

void lerBotaoFalha() {
  static bool anterior = HIGH;
  static uint32_t ultimaBordaMs = 0;
  bool atual = digitalRead(PINO_FALHA);
  if (atual == LOW && anterior == HIGH && millis() - ultimaBordaMs > 300) {
    ultimaBordaMs = millis();
    alternarFalhaSimulada();
  }
  anterior = atual;
}

void lerComandoSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'f' || c == 'F') alternarFalhaSimulada();
  }
}

/* == 8. EVENTO =========================================================== */

void emitirEvento(const char* tipo, uint32_t agora, const char* razao,
                  float fcMedia, EstadoMovimento mov, float cobFc, float cobMov) {
  sequenceEvento++;

  char valor[16];
  if (isnan(fcMedia)) strcpy(valor, "null");
  else                snprintf(valor, sizeof(valor), "%.1f", fcMedia);

  char payload[440];
  snprintf(payload, sizeof(payload),
    "{\"schemaVersion\":%d,\"eventType\":\"%s\",\"eventId\":\"%s-%s-%lu\","
    "\"deviceId\":\"%s\",\"entityId\":\"%s\",\"bootId\":\"%s\",\"eventTimeMs\":%lu,\"sequence\":%lu,"
    "\"value\":%s,\"unit\":\"bpm\",\"state\":\"%s\",\"motion\":\"%s\","
    "\"coverageFc\":%.2f,\"coverageMov\":%.2f,\"reason\":\"%s\"}",
    SCHEMA_VERSION, tipo, DEVICE_ID, bootId, sequenceEvento,
    DEVICE_ID, ENTITY_ID, bootId, agora, sequenceEvento,
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

// Um unico LED: apagado = NORMAL, aceso = ATENCAO,
// piscando = DADOS_INSUFICIENTES (ou ainda sem a primeira avaliacao).
bool ledPiscando() {
  return estadoAtual != EST_NORMAL && estadoAtual != EST_ATENCAO;
}

void atualizarAtuacao() {
  if (!ledPiscando()) digitalWrite(PINO_LED, estadoAtual == EST_ATENCAO ? HIGH : LOW);
  digitalWrite(PINO_BUZZER, alertaAtivo ? HIGH : LOW);
}

void piscarLed(uint32_t agora) {
  static uint32_t ultimaTrocaMs = 0;
  static bool aceso = false;
  if (!ledPiscando() || agora - ultimaTrocaMs < PISCA_LED_MS) return;
  ultimaTrocaMs = agora;
  aceso = !aceso;
  digitalWrite(PINO_LED, aceso ? HIGH : LOW);
}


/* == 11. SETUP =========================================================== */

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(PINO_BOTAO, INPUT_PULLUP);
  pinMode(PINO_FALHA, INPUT_PULLUP);
  pinMode(PINO_LED, OUTPUT); pinMode(PINO_BUZZER, OUTPUT);

  limparJanelas();
  atualizarAtuacao();

  Serial.println();
  Serial.println("=== MARCO 3 | PRODUTOR | ESP32 -> HTTP REST ===");
  Serial.printf("API: %s\n", API_BASE_URL);
  if (strstr(API_BASE_URL, "COLE-AQUI") != NULL) {
    Serial.println("[setup] ATENCAO: cole em config.h a URL https:// do tunel");
  }
  Serial.printf("janelas: FC %ds, MOV %ds | passo %ds | modo demo: %s\n",
                JANELA_FC_S, JANELA_MOV_S, PASSO_AVALIACAO_MS / 1000,
                MODO_DEMO ? "SIM" : "NAO");
  snprintf(bootId, sizeof(bootId), "%08lX", (unsigned long)esp_random());
  Serial.printf("bootId: %s\n", bootId);

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

  configTime(0, 0, "pool.ntp.org", "time.google.com");
  Serial.println("[setup] HTTPS: sincronizacao de horario (NTP) iniciada");

  uint32_t agora = millis();
  proximaAmostraMs   = agora;
  proximaAvaliacaoMs = agora + PASSO_AVALIACAO_MS;
  entrouNoEstadoMs   = agora;
  proximoHeartbeatMs = agora + HEARTBEAT_MS;
}


/* == 12. LOOP ============================================================ */

bool chegouAHora(uint32_t agora, uint32_t &proximo, uint32_t periodo) {
  if ((int32_t)(agora - proximo) < 0) return false;
  proximo += periodo;
  return true;
}

void loop() {
  uint32_t agora = millis();

  lerBotaoFalha();
  lerComandoSerial();
  piscarLed(agora);

  // Comunicacao separada da regra local de alerta.
  if (WiFi.status() != WL_CONNECTED &&
      (int32_t)(agora - proximaWiFiMs) >= 0) {
    WiFi.reconnect();
    proximaWiFiMs = millis() + WIFI_RETRY_MS;
  }
  enviarDaFila(agora);
  enviarHeartbeat(agora);

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
    Serial.printf(" mov=%s estado=%s persistencia=%u/%u wifi=%s fila=%u\n",
                  nomeMovimento(mov), nomeEstado(estadoAtual),
                  avaliacoesCondicao, AVALIACOES_PARA_ENTRAR,
                  (WiFi.status() == WL_CONNECTED && !falhaSimulada) ? "OK" : "FALHA", filaTamanho());
  }
}
