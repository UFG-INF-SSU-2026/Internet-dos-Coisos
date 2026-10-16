/* ==========================================================================
 *  MARCO 3 - ESP32 (Wokwi, Arduino C++)  |  Internet dos Coisos
 *
 *  O ESP32 agora so MEDE e ATUA. A analise (janela, cobertura, histerese)
 *  foi para a API em Python: marco3/api/regra.py.
 *
 *  Ciclo 1: mede a cada 1 s; a cada 3 leituras, POST /api/leituras.
 *           A resposta traz o estado decidido pela API -> LED e buzzer.
 *  Ciclo 2: a cada 3 s, GET /api/dispositivo/comando.
 *           RECONHECER_ALERTA -> silencia o buzzer -> POST /api/dispositivo/comando/ack.
 *  Sem resposta da API por 8 s: MODO LOCAL (regra minima aqui mesmo).
 *
 *  Toda requisicao e HTTPS com certificado validado + chave X-Device-Key.
 *  O potenciometro NAO e um sensor cardiaco real.
 * ========================================================================== */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include "config.h"            // API_BASE_URL e DEVICE_API_KEY (gerado por gerar_config.py, NAO versionar)
#include "certificados_raiz.h" // raizes publicas usadas para validar o HTTPS

/* == CONFIGURACAO ======================================================== */

const char* WIFI_SSID = "Wokwi-GUEST";
const char* DEVICE_ID = "esp32-borda-01";
const char* ENTITY_ID = "patient-0042";

const uint8_t PINO_FC     = 34;  // potenciometro: FC simulada
const uint8_t PINO_SENSOR = 15;  // botao verde: simula sensor desconectado (leitura null)
const uint8_t PINO_FALHA  = 13;  // botao vermelho: simula queda da rede
const uint8_t PINO_LED    = 25;  // apagado=NORMAL, aceso=ATENCAO, piscando=sem dados
const uint8_t PINO_BUZZER = 4;

// Tempos curtos para a demonstracao de 5 min.
const uint32_t AMOSTRA_MS        = 1000;
const uint8_t  LEITURAS_POR_LOTE = 3;      // um lote a cada 3 s
const uint32_t COMANDO_MS        = 3000;   // intervalo do polling do ciclo 2 (escolha do grupo)
const uint32_t MODO_LOCAL_MS     = 8000;   // sem resposta da API por 8 s -> modo local
const uint32_t TIMEOUT_HTTP_MS   = 5000;
const uint32_t WIFI_RETRY_MS     = 10000;

const float FC_ESCALA_MAX   = 250.0;
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

float lerFc() {
  if (digitalRead(PINO_SENSOR) == LOW) return NAN;
  return analogRead(PINO_FC) / 4095.0 * FC_ESCALA_MAX;
}

float lerAceleracaoG() {
  if (!mpuPresente || digitalRead(PINO_SENSOR) == LOW) return NAN;
  sensors_event_t a, gyro, temp;
  if (!mpu.getEvent(&a, &gyro, &temp)) return NAN;
  return sqrt(a.acceleration.x * a.acceleration.x + a.acceleration.y * a.acceleration.y +
              a.acceleration.z * a.acceleration.z) / GRAVIDADE;
}

/* == 2. HTTPS ============================================================ */

// Toda requisicao passa por aqui: TLS validando o certificado do servidor com
// certificados_raiz.h (nunca setInsecure) e a chave do dispositivo no cabecalho.
// corpo == nullptr -> GET; senao -> POST com JSON.
int requisicaoHttps(const String& rota, const char* corpo, String& resposta) {
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
  http.addHeader("X-Device-Key", DEVICE_API_KEY);
  int codigo;
  if (corpo) {
    http.addHeader("Content-Type", "application/json");
    codigo = http.POST((uint8_t*)corpo, strlen(corpo));
  } else {
    codigo = http.GET();
  }
  if (codigo > 0) resposta = http.getString();
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
  int codigo = requisicaoHttps("/api/leituras", corpo, resposta);
  char novo[24];
  if (codigo == 200 && extrairCampo(resposta, "estado", novo, sizeof(novo))) {
    if (estado != novo) Serial.printf("[%lu] estado (API): %s -> %s\n", millis(), estado.c_str(), novo);
    estado = novo;
  }
  // Sem fila (decisao D12): lote que falhou e descartado; a API mostra DADOS_INSUFICIENTES.
  Serial.printf("[%lu] lote %lu: HTTP %d%s\n", millis(), (unsigned long)loteSeq, codigo,
                codigo == 200 ? "" : " (descartado)");
}

/* == 4. CICLO 2: consumir comando do cuidador e produzir o ack =========== */

void consultarComando() {
  String rota = String("/api/dispositivo/comando?deviceId=") + DEVICE_ID + "&entityId=" + ENTITY_ID;
  String resposta;
  char id[24], tipo[24];
  if (requisicaoHttps(rota, nullptr, resposta) != 200) return;
  if (!extrairCampo(resposta, "commandId", id, sizeof(id)) ||
      !extrairCampo(resposta, "tipo", tipo, sizeof(tipo))) return;   // {} = nenhum comando

  // Reconhecer so silencia o buzzer: o LED continua aceso e o estado nao muda.
  if (strcmp(tipo, "RECONHECER_ALERTA") == 0) buzzerSilenciado = true;

  char corpo[160];
  snprintf(corpo, sizeof(corpo), "{\"deviceId\":\"%s\",\"entityId\":\"%s\",\"commandId\":\"%s\"}",
           DEVICE_ID, ENTITY_ID, id);
  int codigo = requisicaoHttps("/api/dispositivo/comando/ack", corpo, resposta);
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
  digitalWrite(PINO_BUZZER, atencao && !buzzerSilenciado);
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
  }
}

/* == SETUP E LOOP ======================================================== */

void setup() {
  Serial.begin(115200);
  pinMode(PINO_SENSOR, INPUT_PULLUP);
  pinMode(PINO_FALHA, INPUT_PULLUP);
  pinMode(PINO_LED, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);

  Serial.println("\n=== MARCO 3 | ESP32 -> HTTPS -> API ===");
  Serial.printf("API: %s\n", API_BASE_URL);
  if (strstr(API_BASE_URL, "COLE-AQUI")) Serial.println("ATENCAO: cole em config.h a URL https:// do tunel");
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
  configTime(0, 0, "pool.ntp.org", "time.google.com");   // relogio certo para validar o certificado

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
    ultimaFc = fcLote[nLote] = lerFc();
    ultimaG  = gLote[nLote]  = lerAceleracaoG();
    Serial.printf("[%lu] fc=%.1f g=%.2f estado=%s%s\n", agora, ultimaFc, ultimaG,
                  estado.c_str(), modoLocal ? " (MODO LOCAL)" : "");
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
