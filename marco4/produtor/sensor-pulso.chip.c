// Sensor de pulso optico (PPG) simulado para o Wokwi - Marco 4, Internet dos Coisos.
//
// Um sensor real (MAX30102, Pulse Sensor) nao entrega a FC: entrega a onda de pulso,
// e quem mede a FC e o ESP32, detectando os batimentos. Este chip faz o papel do
// dedo + sensor: gera em OUT a onda de um coracao no ritmo pedido.
//
//   BPM     (analogico) potenciometro: 0-100% de VCC -> 0-250 bpm (o "coracao" do paciente)
//   R0, R1  (digitais)  ritmo fixo da bancada de teste: 00 = potenciometro, 01 = 78 bpm,
//                       10 = 135 bpm (o Wokwi nao simula o DAC do ESP32)
//   DEDO    (digital)   LOW = sensor fora do dedo: so ruido, nenhum batimento
//   MOV     (digital)   HIGH = paciente em movimento: artefato de baixa frequencia na onda
//   OUT     (analogico) onda de pulso, proporcional a VCC
//
// As tensoes sao lidas e escritas em proporcao ao VCC medido, como num divisor resistivo:
// assim o resultado nao depende da referencia analogica do simulador.
//
// O artefato de movimento e o problema conhecido dos sensores opticos: o balanco do
// braco cria picos falsos, e a FC medida durante o movimento nao e confiavel.
//
// Compilar para o Wokwi do VS Code (o wokwi.com compila sozinho):
//   clang --target=wasm32-unknown-wasip1 --sysroot <wasi-sdk>/share/wasi-sysroot -O2 \
//     -nostartfiles -Wl,--import-memory -Wl,--export-table -Wl,--no-entry -Werror \
//     -I <pasta com wokwi-api.h> -o sensor-pulso.chip.wasm sensor-pulso.chip.c

#include "wokwi-api.h"
#include <math.h>
#include <stdlib.h>

#define PERIODO_US      10000    // atualiza a saida a cada 10 ms (100 Hz; o ESP32 le a 50 Hz)
#define LEITURAS_A_CADA 10       // entradas analogicas mudam devagar: le a cada 100 ms
#define ESCALA_BPM      250.0    // mesma escala do potenciometro do Marco 3
#define LINHA_BASE_V    1.0
#define AMPLITUDE_V     1.2      // altura do pico sistolico
#define RUIDO_V         0.03     // ruido eletrico sempre presente
#define ARTEFATO_V      0.9      // balanco do braco
#define ARTEFATO_HZ     1.7      // ~ ritmo de uma caminhada

typedef struct {
  pin_t vcc_pin, out, bpm, r0, r1, dedo, mov;
  double fase;            // posicao no ciclo cardiaco, de 0 a 1
  double fase_artefato;
  uint64_t ultimo_ns;
  uint32_t semente;
  uint32_t passos;
  double vcc, bpm_pot;    // ultimas leituras analogicas
} chip_state_t;

// Ruido uniforme em [-1, 1] (gerador congruente: deterministico e sem libc extra).
static double ruido(chip_state_t *c) {
  c->semente = c->semente * 1664525u + 1013904223u;
  return (double)(c->semente >> 8) / 8388608.0 - 1.0;
}

// Forma do pulso: pico sistolico e o pico menor apos a incisura dicrotica.
static double pulso(double f) {
  double sistolico = exp(-pow((f - 0.15) / 0.06, 2));
  double dicrotico = 0.35 * exp(-pow((f - 0.45) / 0.08, 2));
  return sistolico + dicrotico;
}

static void atualizar(void *dados) {
  chip_state_t *c = (chip_state_t *)dados;
  uint64_t agora = get_sim_nanos();
  double dt = (double)(agora - c->ultimo_ns) / 1e9;
  c->ultimo_ns = agora;

  if (c->passos++ % LEITURAS_A_CADA == 0) {        // ler o ADC custa caro no simulador
    c->vcc = pin_adc_read(c->vcc_pin);
    if (c->vcc < 0.5) c->vcc = 3.3;                 // sem alimentacao lida: assume 3,3 V
    c->bpm_pot = pin_adc_read(c->bpm) / c->vcc * ESCALA_BPM;
  }
  double vcc = c->vcc, bpm;
  switch ((pin_read(c->r1) << 1) | pin_read(c->r0)) {
    case 1: bpm = 78.0; break;
    case 2: bpm = 135.0; break;
    default: bpm = c->bpm_pot;
  }

  double v = LINHA_BASE_V + RUIDO_V * ruido(c);
  if (pin_read(c->dedo) && bpm >= 1.0) {
    c->fase += dt * bpm / 60.0;
    c->fase -= floor(c->fase);
    v += AMPLITUDE_V * pulso(c->fase);
  }
  if (pin_read(c->mov)) {
    c->fase_artefato += dt * ARTEFATO_HZ;
    c->fase_artefato -= floor(c->fase_artefato);
    v += ARTEFATO_V * sin(2.0 * M_PI * c->fase_artefato) + 0.4 * ruido(c);
  }
  if (v < 0.0) v = 0.0;
  if (v > 3.3) v = 3.3;
  pin_dac_write(c->out, (float)(v / 3.3 * vcc));    // em proporcao ao VCC
}

void chip_init(void) {
  chip_state_t *c = calloc(1, sizeof(chip_state_t));
  c->vcc_pin = pin_init("VCC", ANALOG);
  c->out = pin_init("OUT", ANALOG);
  c->bpm = pin_init("BPM", ANALOG);
  c->r0 = pin_init("R0", INPUT_PULLDOWN);
  c->r1 = pin_init("R1", INPUT_PULLDOWN);
  c->dedo = pin_init("DEDO", INPUT_PULLUP);    // desligado = dedo no sensor
  c->mov = pin_init("MOV", INPUT_PULLDOWN);    // desligado = sem movimento
  c->semente = 20261127u;
  c->ultimo_ns = get_sim_nanos();

  const timer_config_t cfg = { .user_data = c, .callback = atualizar };
  timer_start(timer_init(&cfg), PERIODO_US, true);
}
