# Comparação dos protótipos individuais

Antes de definir a fronteira, o grupo comparou os protótipos do Marco 1 pelo
comportamento executável, não pelo relatório.

## Protótipos considerados

| | Matheus Augusto | Murilo Bernardo |
|---|---|---|
| Responsabilidade | estado e processamento temporal | decisão e atuação |
| Grandeza | frequência cardíaca (bpm) | inclinação (graus) |
| Entrada | potenciômetro (substituta) + MPU6050 | potenciômetro (substituta) + chave |
| `eventType` | `vitals.state.changed` | `smartclothing.inclinacao` |
| Estados | 4 | 7 |
| Qualidade | `coverageFc` / `coverageMov` | `valid` / `quality` |
| Emissão | apenas em transição de estado | a cada amostra (250 ms) |
| Atuação | LED RGB + buzzer | 3 LEDs + buzzer + rearme manual |

## Decisões preservadas, adaptadas e descartadas

**Preservadas.** Do protótipo de estado e tempo: janela deslizante, cobertura
mínima, persistência e razão explícita da transição. Do protótipo de decisão e
atuação: histerese com limiares distintos de entrada e saída, expiração do dado
e distinção entre alerta e falha de sensor.

**Adaptadas.** O contrato do evento ganhou `schemaVersion`, ausente nos dois
protótipos. Sem versão declarada, qualquer mudança de campo quebraria o
consumidor silenciosamente.

**Descartada nesta fronteira.** A emissão a cada amostra. Publicar quatro
eventos por segundo em um broker transforma o tópico em ruído e desperdiça
banda de um dispositivo restrito. A telemetria contínua é útil localmente, no
monitor serial; na fronteira, publica-se a transição de estado.

## Incompatibilidades identificadas

Os dois protótipos usam `deviceId` e `entityId` diferentes para o mesmo
sistema, unidades diferentes (bpm e graus) e vocabulários de estado que não se
sobrepõem. Integrar os dois exigiria um contrato comum que ainda não existe.

## Por que apenas um protótipo atravessa esta fronteira

O Marco 2 pede a validação de **uma** fronteira real, não do sistema completo.
Escolhemos a fronteira produtor → consumidor porque ela já existe na modelagem
da Atividade 02: o dispositivo decide na borda e publica o resultado para
destinos que não conhece.

O protótipo de decisão e atuação é o próximo passo natural: receberia o comando
publicado pelo produtor e usaria o botão de rearme como confirmação humana —
a distinção entre telemetria e comando discutida na Aula 05. Isso exige
unificar o vocabulário de estados e definir autorização e idempotência do
comando, trabalho que fica para a etapa seguinte.
