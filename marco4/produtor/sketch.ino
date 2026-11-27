/* ==========================================================================
 *  MARCO 4 - ESP32 (Wokwi, Arduino C++)  |  Internet dos Coisos
 *
 *  O ESP32 so MEDE e ATUA. A analise (janela, cobertura, histerese)
 *  fica na API em Python: marco4/api/regra.py.
 *
 *  FC medida pela onda de pulso (Marco 4): o chip sensor-pulso simula um sensor
 *  optico (PPG). Uma tarefa le a onda a 50 Hz, detecta os batimentos e calcula a
 *  FC pela mediana dos ultimos intervalos, como se faz com um MAX30102 real.
 *
 *  Ciclo 1: mede a cada 1 s; a cada 3 leituras, POST /api/leituras.
 *           A resposta traz o estado decidido pela API -> LED e buzzer.
 *  Ciclo 2: a cada 3 s, GET /api/dispositivo/comando.
 *           RECONHECER_ALERTA -> silencia o buzzer -> POST /api/dispositivo/comando/ack.
 *  Sem resposta da API por 8 s: MODO LOCAL (regra minima aqui mesmo).
 *
 *  Toda requisicao vai assinada (HMAC-SHA256 com a chave do dispositivo).
 *  Os sinais sao simulados e nao tem valor clinico.
 * ========================================================================== */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <time.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include "mbedtls/md.h"        // HMAC-SHA256
#include "esp_sntp.h"          // intervalo de re-sincronizacao do relogio
#include "config.h"            // URL e chave PRIVADA geradas por gerar_config.py

/* == CONFIGURACAO ======================================================== */

const char* WIFI_SSID = "Wokwi-GUEST";
const char* DEVICE_ID = "esp32-borda-01";
const char* ENTITY_ID = "patient-0042";

const uint8_t PINO_PULSO  = 34;  // onda de pulso do chip sensor-pulso (ADC1)
const uint8_t PINO_R0     = 26;  // bancada: ritmo fixo do coracao simulado (R1R0: 00 = potenciometro,
const uint8_t PINO_R1     = 33;  //          01 = 78 bpm, 10 = 135 bpm); o Wokwi nao simula o DAC
const uint8_t PINO_DEDO   = 27;  // bancada: LOW = sensor fora do dedo (cenario 3)
const uint8_t PINO_MOV    = 14;  // bancada: HIGH = artefato de movimento na onda
const uint8_t PINO_FALHA  = 13;  // botao vermelho "rede off": simula queda da rede
const uint8_t PINO_LED    = 25;  // apagado=NORMAL, aceso=ATENCAO, piscando=sem dados
const uint8_t PINO_BUZZER = 4;

// Tempos curtos para a demonstracao de 5 min.
const uint32_t AMOSTRA_MS        = 1000;
const uint8_t  LEITURAS_POR_LOTE = 3;      // um lote a cada 3 s
const uint32_t COMANDO_MS        = 3000;   // intervalo do polling do ciclo 2 (escolha do grupo)
const uint32_t MODO_LOCAL_MS     = 8000;   // sem resposta da API por 8 s -> modo local
const uint32_t TIMEOUT_HTTP_MS   = 5000;
const uint32_t WIFI_RETRY_MS     = 10000;

const float FC_ESCALA_MAX   = 250.0;  // 3,3 V no BPM/AJUSTE do chip = 250 bpm

// Deteccao de batimentos na onda de pulso.
const uint32_t PULSO_AMOSTRA_MS       = 20;    // 50 Hz
const uint32_t PULSO_REFRATARIO_MS    = 300;   // ignora o pico dicrotico; ate 200 bpm
const uint32_t PULSO_SEM_BATIMENTO_MS = 3000;  // 3 s sem batimento: FC invalida (null)
const uint8_t  PULSO_INTERVALOS       = 5;     // FC = 60 / mediana dos ultimos 5 intervalos
const float    PULSO_AMPLITUDE_MIN_V  = 0.15;  // abaixo disso e so ruido (sem dedo)
const float    PULSO_LIMIAR           = 0.6;   // batimento: sobe acima de 60% da envoltoria
const float    PULSO_DECAIMENTO       = 0.02;  // envoltoria acompanha o sinal em ~1 s
const float FC_LIMIAR_LOCAL = 100.0;
const float GRAVIDADE       = 9.80665;

/* == ESTADO ============================================================== */

Adafruit_MPU6050 mpu;
bool mpuPresente = false;
char bootId[12];               // muda a cada reinicio: loteId nao se repete
uint32_t loteSeq = 0;

float fcLote[LEITURAS_POR_LOTE], gLote[LEITURAS_POR_LOTE];
uint8_t nLote = 0;
float ultimaFc = NAN, ultimaG = NAN;

String estado = "SEM_DADOS";   // ultimo estado decidido pela API
bool buzzerSilenciado = false; // ciclo 2: cuidador reconheceu o alerta
bool modoLocal = false;
bool falhaSimulada = false;

uint32_t ultimaRespostaMs = 0, proximaAmostraMs = 0, proximoComandoMs = 0, proximoWiFiMs = 0;

/* == 1. MEDIR ============================================================ */

// Cenarios didaticos acionados pelo Monitor Serial: 0=potenciometro/MPU;
// 1=normal; 2=FC alta em repouso; 3=sensor ausente; 4=movimento;
// a=ciclo automatico de 65 s. A simulacao nunca representa dados clinicos.
char cenario = '0';
uint32_t inicioCicloMs = 0;

char cenarioEmExecucao() {
  if (cenario != 'a') return cenario;
  uint32_t seg = ((millis() - inicioCicloMs) / 1000) % 65;
  if (seg < 15) return '1';     // Normal por 15 s
  if (seg < 35) return '2';     // FC alta e repouso por 20 s
  if (seg < 45) return '3';     // Sensor ausente por 10 s
  return '1';                 // Recuperacao por 20 s
}

// --- Sensor de pulso: tarefa propria, para o HTTP do loop nao atrapalhar a amostragem ---
volatile float fcMedida = NAN;
volatile uint32_t batimentos = 0;
volatile float pulsoMin = NAN, pulsoMax = NAN;   // envoltoria da onda (diagnostico na serial)

float medianaMs(const uint32_t* v, uint8_t n) {
  uint32_t o[PULSO_INTERVALOS];
  for (uint8_t i = 0; i < n; i++) o[i] = v[i];
  for (uint8_t i = 1; i < n; i++)
    for (uint8_t j = i; j > 0 && o[j - 1] > o[j]; j--) { uint32_t t = o[j]; o[j] = o[j - 1]; o[j - 1] = t; }
  return n % 2 ? o[n / 2] : (o[n / 2 - 1] + o[n / 2]) / 2.0;
}

void tarefaPulso(void*) {
  float y = 1.0, maximo = 1.0, minimo = 1.0;
  bool acima = false;
  uint32_t ultimoBatimento = 0, intervalos[PULSO_INTERVALOS];
  uint8_t n = 0, i = 0;
  TickType_t proxima = xTaskGetTickCount();
  for (;;) {
    vTaskDelayUntil(&proxima, pdMS_TO_TICKS(PULSO_AMOSTRA_MS));
    uint32_t agora = millis();
    y += 0.5 * (analogRead(PINO_PULSO) * 3.3 / 4095.0 - y);     // passa-baixa leve
    // Envoltoria: sobe na hora com o sinal e desce devagar.
    if (y > maximo) maximo = y; else maximo -= (maximo - y) * PULSO_DECAIMENTO;
    if (y < minimo) minimo = y; else minimo += (y - minimo) * PULSO_DECAIMENTO;
    float amplitude = maximo - minimo;
    pulsoMin = minimo;
    pulsoMax = maximo;
    bool agoraAcima = y > minimo + PULSO_LIMIAR * amplitude;
    if (agoraAcima && !acima && amplitude > PULSO_AMPLITUDE_MIN_V &&
        agora - ultimoBatimento > PULSO_REFRATARIO_MS) {
      if (ultimoBatimento && agora - ultimoBatimento < PULSO_SEM_BATIMENTO_MS) {
        intervalos[i] = agora - ultimoBatimento;
        i = (i + 1) % PULSO_INTERVALOS;
        if (n < PULSO_INTERVALOS) n++;
      }
      ultimoBatimento = agora;
      batimentos++;
      if (n >= 3) fcMedida = 60000.0 / medianaMs(intervalos, n);
    }
    acima = agoraAcima;
    if (!ultimoBatimento || agora - ultimoBatimento > PULSO_SEM_BATIMENTO_MS) {
      fcMedida = NAN;      // sem dedo, sem coracao ou sinal so com ruido
      n = 0;
    }
  }
}

float lerFc() { return fcMedida; }

// --- Bancada de teste ---
// Os cenarios do Monitor Serial nao escrevem a FC: escolhem o ritmo do coracao simulado no
// chip (R0/R1), tiram o dedo do sensor (DEDO) ou ligam o artefato de movimento (MOV).
// A FC continua medida pela onda. No modo manual, o potenciometro define o ritmo, e o MOV
// acompanha o MPU6050: o balanco que o acelerometro mede tambem perturba o sensor optico.
void ajustarBancada(float g) {
  uint8_t ritmo = 0;        // 0 = potenciometro, 1 = 78 bpm, 2 = 135 bpm
  bool dedo = true, mov = false;
  switch (cenarioEmExecucao()) {
    case '1': ritmo = 1; break;
    case '2': ritmo = 2; break;
    case '3': ritmo = 1; dedo = false; break;
    case '4': ritmo = 2; mov = true; break;
    default: mov = !isnan(g) && fabs(g - 1.0) > 0.15;
  }
  digitalWrite(PINO_R0, ritmo & 1 ? HIGH : LOW);
  digitalWrite(PINO_R1, ritmo & 2 ? HIGH : LOW);
  digitalWrite(PINO_DEDO, dedo ? HIGH : LOW);
  digitalWrite(PINO_MOV, mov ? HIGH : LOW);
}

float lerAceleracaoG() {
  switch (cenarioEmExecucao()) {
    case '1': case '2': case '3': return 1.0;
    case '4': return 1.75;
  }
  if (!mpuPresente) return NAN;
  sensors_event_t a, gyro, temp;
  if (!mpu.getEvent(&a, &gyro, &temp)) return NAN;
  return sqrt(a.acceleration.x * a.acceleration.x + a.acceleration.y * a.acceleration.y +
              a.acceleration.z * a.acceleration.z) / GRAVIDADE;
}

/* == 2. HTTP ASSINADO ==================================================== */

// Assinatura HMAC-SHA256 da mensagem com a chave do dispositivo (decisao D17):
//   HMAC(chave, horario + "\n" + METODO + " " + rota + "\n" + corpo)
// A chave nunca trafega. A API recalcula: chave errada ou corpo alterado -> 401;
// horario com mais de 120 s -> 401 (replays dentro da janela ainda sao possiveis).
// Relogio (D35): o NTP acerta a hora no boot, mas no Wokwi a simulacao anda a ~35% do tempo
// real e o relogio do ESP32 fica para tras; se o NTP falha (DNS), a diferenca passa de 120 s
// e a API recusa tudo com 401. Cada resposta HTTP da API traz o cabecalho Date, usado para
// corrigir a diferenca (resolucao de 1 s, bem dentro da janela).
long ajusteRelogioS = 0;

// Quando o NTP consegue sincronizar, o relogio ja esta certo: o ajuste pelo Date volta a zero
// (senao os dois se somavam e o lote seguinte saia adiantado, com 401).
void relogioSincronizado(struct timeval*) { ajusteRelogioS = 0; }

void corrigirRelogio(const String& data) {   // "Thu, 27 Nov 2026 21:30:00 GMT"
  struct tm t = {};
  if (data.length() == 0 || !strptime(data.c_str(), "%a, %d %b %Y %H:%M:%S", &t)) return;
  long diferenca = (long)(mktime(&t) - time(nullptr));   // TZ em UTC: configTime(0, 0)
  if (labs(diferenca - ajusteRelogioS) <= 2) return;
  if (labs(diferenca - ajusteRelogioS) >= 10)
    Serial.printf("[%lu] relogio corrigido pela API: %+ld s\n", millis(), diferenca);
  ajusteRelogioS = diferenca;
}

void assinar(const char* metodo, const String& rota, const char* corpo, char* horario, char* hex) {
  snprintf(horario, 12, "%lu", (unsigned long)(time(nullptr) + ajusteRelogioS));
  String mensagem = String(horario) + "\n" + metodo + " " + rota + "\n" + (corpo ? corpo : "");
  uint8_t mac[32];
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),
                  (const uint8_t*)DEVICE_API_KEY, strlen(DEVICE_API_KEY),
                  (const uint8_t*)mensagem.c_str(), mensagem.length(), mac);
  for (int i = 0; i < 32; i++) sprintf(hex + 2 * i, "%02x", mac[i]);
}

// Toda requisicao passa por aqui. corpo == nullptr -> GET; senao -> POST com JSON.
int requisicao(const String& rota, const char* corpo, String& resposta) {
  if (falhaSimulada || WiFi.status() != WL_CONNECTED) return -1;
  String base = String(API_BASE_URL);
  if (base.endsWith("/")) base.remove(base.length() - 1);
  char horario[12], assinatura[65];
  assinar(corpo ? "POST" : "GET", rota, corpo, horario, assinatura);

  WiFiClient cliente;
  HTTPClient http;
  http.setConnectTimeout(TIMEOUT_HTTP_MS);
  http.setTimeout(TIMEOUT_HTTP_MS);
  if (!http.begin(cliente, base + rota)) return -1;
  http.addHeader("X-Timestamp", horario);
  http.addHeader("X-Assinatura", assinatura);
  const char* cabecalhos[] = {"Date"};
  http.collectHeaders(cabecalhos, 1);
  int codigo;
  if (corpo) {
    http.addHeader("Content-Type", "application/json");
    codigo = http.POST((uint8_t*)corpo, strlen(corpo));
  } else {
    codigo = http.GET();
  }
  if (codigo > 0) {
    resposta = http.getString();
    corrigirRelogio(http.header("Date"));     // vale tambem para o 401 por horario
  }
  http.end();
  if (codigo == 200 || codigo == 201) ultimaRespostaMs = millis();
  return codigo;
}

// Le "chave":"valor" de um JSON pequeno (evita a biblioteca ArduinoJson).
bool extrairCampo(const String& json, const char* chave, char* saida, size_t n) {
  String busca = String("\"") + chave + "\":\"";
  int i = json.indexOf(busca);
  if (i < 0) return false;
  i += busca.length();
  int f = json.indexOf('"', i);
  if (f < 0 || (size_t)(f - i) >= n) return false;
  json.substring(i, f).toCharArray(saida, n);
  return true;
}

void numeroOuNull(char* s, size_t n, float v, const char* formato) {
  if (isnan(v)) strcpy(s, "null"); else snprintf(s, n, formato, v);
}

/* == 3. CICLO 1: enviar lote e receber o estado ========================== */

void enviarLote() {
  loteSeq++;
  char corpo[400];
  int n = snprintf(corpo, sizeof(corpo),
                   "{\"deviceId\":\"%s\",\"entityId\":\"%s\",\"loteId\":\"%s-%lu\",\"leituras\":[",
                   DEVICE_ID, ENTITY_ID, bootId, (unsigned long)loteSeq);
  for (uint8_t i = 0; i < LEITURAS_POR_LOTE; i++) {
    char fc[12], g[12];
    numeroOuNull(fc, sizeof(fc), fcLote[i], "%.1f");
    numeroOuNull(g, sizeof(g), gLote[i], "%.2f");
    n += snprintf(corpo + n, sizeof(corpo) - n, "%s{\"fc\":%s,\"g\":%s}", i ? "," : "", fc, g);
  }
  snprintf(corpo + n, sizeof(corpo) - n, "]}");

  String resposta;
  int codigo = requisicao("/api/leituras", corpo, resposta);
  char novo[24];
  if (codigo == 200 && extrairCampo(resposta, "estado", novo, sizeof(novo))) {
    if (estado != novo) Serial.printf("[%lu] estado (API): %s -> %s\n", millis(), estado.c_str(), novo);
    estado = novo;
  }
  // Sem fila OFFLINE no dispositivo (D12). A FILA NOVA fica na API,
  // entre recebimento HTTP e processamento: lote que nao saiu do ESP32 e perdido.
  Serial.printf("[%lu] lote %lu: HTTP %d%s\n", millis(), (unsigned long)loteSeq, codigo,
                codigo == 200 ? "" : " (descartado)");
}

/* == 4. CICLO 2: consumir comando do cuidador e produzir o ack =========== */

void consultarComando() {
  String rota = String("/api/dispositivo/comando?deviceId=") + DEVICE_ID + "&entityId=" + ENTITY_ID;
  String resposta;
  char id[24], tipo[24];
  if (requisicao(rota, nullptr, resposta) != 200) return;
  if (!extrairCampo(resposta, "commandId", id, sizeof(id)) ||
      !extrairCampo(resposta, "tipo", tipo, sizeof(tipo))) return;   // {} = nenhum comando

  // Reconhecer so silencia o buzzer: o LED continua aceso e o estado nao muda.
  if (strcmp(tipo, "RECONHECER_ALERTA") == 0) buzzerSilenciado = true;

  char corpo[160];
  snprintf(corpo, sizeof(corpo), "{\"deviceId\":\"%s\",\"entityId\":\"%s\",\"commandId\":\"%s\"}",
           DEVICE_ID, ENTITY_ID, id);
  int codigo = requisicao("/api/dispositivo/comando/ack", corpo, resposta);
  Serial.printf("[%lu] comando %s (%s): buzzer silenciado; ack HTTP %d\n", millis(), id, tipo, codigo);
}

/* == 5. ATUAR ============================================================ */

// Modo local: regra minima com a ultima leitura (FC alta em repouso).
bool alertaLocal() {
  return !isnan(ultimaFc) && ultimaFc > FC_LIMIAR_LOCAL &&
         !isnan(ultimaG) && fabs(ultimaG - 1.0) <= 0.15;
}

void atualizarAtuacao(uint32_t agora) {
  bool atencao = modoLocal ? alertaLocal() : estado == "ATENCAO";
  bool normal  = !modoLocal && estado == "NORMAL";
  if (!atencao) buzzerSilenciado = false;        // o silencio vale so para o alerta atual

  if (atencao)     digitalWrite(PINO_LED, HIGH);
  else if (normal) digitalWrite(PINO_LED, LOW);
  else             digitalWrite(PINO_LED, (agora / 500) % 2);   // piscando
  // O buzzer e piezo: so soa com onda quadrada (tone), nao com nivel fixo (digitalWrite).
  static bool tocando = false;
  bool tocar = atencao && !buzzerSilenciado;
  if (tocar != tocando) {
    if (tocar) tone(PINO_BUZZER, 1000); else noTone(PINO_BUZZER);
    tocando = tocar;
  }
}

/* == 6. FALHA SIMULADA (botao vermelho ou tecla 'f') ===================== */

void alternarFalha() {
  falhaSimulada = !falhaSimulada;
  Serial.println(falhaSimulada ? "FALHA SIMULADA: sem rede" : "FALHA SIMULADA ENCERRADA");
}

void lerFalha() {
  static bool anterior = HIGH;
  static uint32_t ultimaBordaMs = 0;
  bool atual = digitalRead(PINO_FALHA);
  if (atual == LOW && anterior == HIGH && millis() - ultimaBordaMs > 300) {
    ultimaBordaMs = millis();
    alternarFalha();
  }
  anterior = atual;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'f' || c == 'F') alternarFalha();
    if (c == '0' || c == '1' || c == '2' || c == '3' || c == '4' || c == 'a') {
      cenario = c;
      inicioCicloMs = millis();
      Serial.printf("CENARIO: %c (0=manual, 1=normal, 2=alerta, 3=sem FC, 4=movimento, a=automatico)\n", c);
    }
  }
}

/* == SETUP E LOOP ======================================================== */

void setup() {
  Serial.begin(115200);
  pinMode(PINO_FALHA, INPUT_PULLUP);
  pinMode(PINO_LED, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);
  pinMode(PINO_R0, OUTPUT);
  pinMode(PINO_R1, OUTPUT);
  pinMode(PINO_DEDO, OUTPUT);
  pinMode(PINO_MOV, OUTPUT);
  ajustarBancada(1.0);
  xTaskCreatePinnedToCore(tarefaPulso, "pulso", 4096, nullptr, 2, nullptr, 0);

  Serial.println("\n=== MARCO 4 | sensor de pulso -> ESP32 -> HTTP assinado -> API ===");
  Serial.println("Cenarios de teste no Serial: 0=manual 1=normal 2=alerta 3=sem sensor 4=movimento a=automatico f=falha de rede");
  Serial.printf("API: %s\n", API_BASE_URL);
  if (strstr(API_BASE_URL, "trycloudflare")) Serial.println("ATENCAO: o tunel redireciona http para https (301); use http://host.wokwi.internal:5000 (D33)");
  snprintf(bootId, sizeof(bootId), "%08lX", (unsigned long)esp_random());
  Serial.printf("bootId: %s\n", bootId);

  Wire.begin();
  mpuPresente = mpu.begin();
  if (mpuPresente) mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  Serial.println(mpuPresente ? "MPU6050 ok" : "MPU6050 ausente");

  Serial.print("WiFi");
  WiFi.begin(WIFI_SSID, "", 6);                 // canal 6 acelera no Wokwi
  while (WiFi.status() != WL_CONNECTED) { delay(200); Serial.print("."); }
  Serial.printf(" conectado, IP %s\n", WiFi.localIP().toString().c_str());
  // A assinatura leva o horario: sem NTP a API recusa as mensagens. Espera ate 10 s.
  // Re-sincroniza a cada 15 s: no Wokwi o relogio simulado atrasa quando a simulacao fica lenta.
  sntp_set_sync_interval(15000);
  sntp_set_time_sync_notification_cb(relogioSincronizado);
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  Serial.print("NTP");
  for (int i = 0; i < 40 && time(nullptr) < 1700000000; i++) { delay(250); Serial.print("."); }
  Serial.println(time(nullptr) >= 1700000000 ? " ok" : " sem horario (a API vai recusar com 401)");

  proximaAmostraMs = proximoComandoMs = ultimaRespostaMs = millis();
}

void loop() {
  uint32_t agora = millis();
  lerFalha();
  if (WiFi.status() != WL_CONNECTED && (int32_t)(agora - proximoWiFiMs) >= 0) {
    WiFi.reconnect();
    proximoWiFiMs = agora + WIFI_RETRY_MS;
  }

  if ((int32_t)(agora - proximaAmostraMs) >= 0) {          // 1 leitura por segundo
    proximaAmostraMs += AMOSTRA_MS;
    ultimaG  = gLote[nLote]  = lerAceleracaoG();
    ajustarBancada(ultimaG);
    ultimaFc = fcLote[nLote] = lerFc();
    Serial.printf("[%lu] fc=%.1f g=%.2f bat=%lu onda=%.2f-%.2fV estado=%s%s\n", agora, ultimaFc,
                  ultimaG, (unsigned long)batimentos, pulsoMin, pulsoMax, estado.c_str(),
                  modoLocal ? " (MODO LOCAL)" : "");
    if (++nLote == LEITURAS_POR_LOTE) { enviarLote(); nLote = 0; }
  }

  if ((int32_t)(agora - proximoComandoMs) >= 0) {          // ciclo 2
    proximoComandoMs = agora + COMANDO_MS;
    consultarComando();
  }

  bool semApi = millis() - ultimaRespostaMs > MODO_LOCAL_MS;
  if (semApi != modoLocal) {
    modoLocal = semApi;
    Serial.println(modoLocal ? "MODO LOCAL: API sem responder; regra minima no ESP32"
                             : "API respondeu: estado volta a vir da API");
  }
  atualizarAtuacao(millis());
}
