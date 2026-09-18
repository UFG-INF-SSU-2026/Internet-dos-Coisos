# Guia de estudo — verificação oral do Marco 2

Material de apoio para explicar a integração na aula de 18/09. Organizado do
mais geral para o mais específico; as respostas curtas no final são para
consulta rápida.

---

## 1. A frase de abertura

> "Integramos **uma fronteira real**: o protótipo de estado e tempo do Marco 1
> (ESP32 no Wokwi) publica por MQTT a decisão que já tomava localmente, e um
> serviço em Python recebe, valida o contrato e produz efeito observável —
> painel de estado e alerta ao cuidador. A condição de falha tratada é o
> broker indisponível: o produtor guarda os eventos numa fila local e
> reenvia em ordem quando reconecta."

Tudo o que vem depois é detalhe dessa frase.

---

## 2. Os quatro termos que a banca vai cobrar

| Termo | O que é | No nosso projeto |
|---|---|---|
| **Protocolo** | regras de comunicação entre participantes | **MQTT** (e TCP/IP por baixo) |
| **Middleware** | software que media a interação e oferece capacidades recorrentes: roteamento, sessão, buffer, entrega | o **broker** `broker.hivemq.com` |
| **Plataforma** | ambiente para executar, operar e observar | Wokwi (simulação) e Python (execução do consumidor). Android seria uma plataforma — não usamos |
| **Framework / biblioteca** | estrutura e abstrações para organizar o código | `PubSubClient` (Arduino) e `paho-mqtt` (Python) são **bibliotecas cliente MQTT** |

Pergunta clássica: *"MQTT é middleware?"* — **Não.** MQTT é o protocolo. O
broker, que é um programa rodando em algum lugar, é o middleware. A
biblioteca que fala MQTT dentro do ESP32 é uma biblioteca cliente.

---

## 3. Como o broker funciona

### 3.1 Modelo publish/subscribe

```
ESP32 ──PUBLISH──▶ broker ──▶ quem assinou o tópico
                              (consumidor Python, e qualquer outro autorizado)
```

- O produtor **não conhece** o consumidor. Ele publica num **tópico** (uma
  string hierárquica) e vai embora.
- O consumidor **assina** o tópico. O broker entrega a cada assinante uma
  cópia do que foi publicado.
- Se ninguém assinou, a publicação é descartada (a menos que seja *retained*).

Isso é o que dá o **desacoplamento espacial**: adicionar um segundo
consumidor (um app do cuidador, um painel) não muda nada no produtor.

### 3.2 A sessão MQTT, pacote por pacote

| Pacote | Quem envia | O que faz | Onde está no nosso código |
|---|---|---|---|
| `CONNECT` | cliente | propõe identidade (`clientId`), *keepalive*, *last will* | `mqtt.connect(clientId, NULL, NULL, TOPICO_STATUS, 1, true, "{...offline}")` em `conectarMqtt()` |
| `CONNACK` | broker | aceita ou rejeita | retorno `true/false` de `mqtt.connect()` |
| `SUBSCRIBE` | assinante | registra filtros de tópico e QoS | `client.subscribe([(TOPICO_STATE, 1), (TOPICO_STATUS, 1)])` em `on_connect` |
| `PUBLISH` | publicador | tópico + payload | `mqtt.publish(TOPICO_STATE, payload)` em `publicar()` |
| `PINGREQ` / `PINGRESP` | cliente / broker | mantém a sessão viva | automático em `mqtt.loop()` |
| `DISCONNECT` | cliente | encerramento limpo (não dispara o *will*) | `mqtt.disconnect()` na falha simulada |

O broker mantém **estado de conexão** (quem está conectado, o que assinou).
Ele **não** mantém o estado do paciente — isso é estado de negócio e fica no
produtor (`estadoAtual`) e no consumidor (`estado_atual`).

### 3.3 Tópicos: parte da interface

```
ufg/ssu/2026-2/internet-das-coisos/patient-0042/state    ← eventos de mudança de estado
ufg/ssu/2026-2/internet-das-coisos/patient-0042/status   ← online / offline do dispositivo
```

- O prefixo `ufg/ssu/2026-2/internet-das-coisos` é o **namespace do grupo**
  no broker público. Sem ele, qualquer outra pessoa usando `patient-0042`
  receberia e enviaria eventos no nosso fluxo.
- `patient-0042` é a **entidade observada**, pseudonimizada.
- `state` e `status` separam **telemetria de negócio** de **disponibilidade
  do dispositivo**. São coisas diferentes: silêncio no `state` pode ser
  "nada mudou" ou "dispositivo caiu"; o `status` desambigua.
- Mudar um tópico publicado quebra assinantes que você não conhece. Por isso
  o nome é estável e igual nos dois lados (`TOPICO_BASE` no sketch, `BASE`
  no Python).

### 3.4 QoS — o que o broker garante e o que não garante

| QoS | Semântica | Custo |
|---|---|---|
| 0 | no máximo uma vez: envia e esquece | menor; pode perder |
| 1 | ao menos uma vez: receptor confirma com `PUBACK`; retransmite se não confirmar | pode **duplicar** |
| 2 | exatamente uma vez naquele enlace | handshake extra |

**Nossa escolha:** produtor publica em QoS 0; consumidor assina em QoS 1.

Por quê: o evento é raro (só na transição de estado), tem `sequence` e
`eventId`, e o produtor tem fila própria para a falha que nos importa
(broker fora). QoS 1 no produtor daria retransmissão pelo broker, mas a
duplicata que ele geraria já é reconhecida pelo consumidor (`eventId` em
`ids_processados`). O ponto que a banca quer ouvir:

> **QoS trata entrega MQTT. Não garante que o consumidor validou, decidiu ou
> atuou.** Entrega ≠ processamento.

### 3.5 Retained e last will

- **Retained:** o broker guarda a última mensagem publicada com a flag
  `retain` e a entrega imediatamente a quem assinar depois. Usamos em
  `status`: um consumidor que sobe **depois** do produtor já vê `online`.
- **Last will:** no `CONNECT` o cliente deixa uma mensagem que o broker
  publica **se a conexão cair sem `DISCONNECT`** (cabo puxado, simulação
  interrompida, *keepalive* estourado). Usamos `{"status":"offline"}` em
  `status`, retained.

Frase para a banca: *"ausência de dado não é ausência de risco — o last will
transforma o silêncio do dispositivo em algo que o consumidor consegue ver."*

### 3.6 Keepalive — e a armadilha do Wokwi

- Cliente declara *keepalive* N segundos no `CONNECT`. Se o broker não
  receber nada em **1,5 × N**, derruba a conexão e publica o *will*.
- O cliente manda `PINGREQ` quando passa N segundos sem tráfego.
- **No Wokwi a simulação roda a ~30% do tempo real** com WiFi. 15 s de
  `millis()` viram ~47 s reais → o PING chegava depois dos 22,5 s → o
  broker derrubava a conexão a cada ~25 s e publicava `offline` sem falha
  real.
- Solução no `sketch.ino`: declara 40 s ao broker
  (`MQTT_KEEPALIVE_BROKER_S`, tolerância de 60 s reais) mas pinga a cada
  10 s simulados (`MQTT_KEEPALIVE_CLIENTE_S`, ~31 s reais). `PubSubClient`
  usa um só valor para os dois, então o código chama `setKeepAlive()` antes
  e depois do `connect()`.

Se perguntarem "por que dois valores?", esta é a resposta. É um bom exemplo
de *"a simulação demonstra X, mas não valida Y"*: o tempo do simulador não
é o tempo do mundo.

---

## 4. O fluxo completo, de ponta a ponta

```
potenciômetro ─┐
               ├─▶ lerFrequenciaCardiaca / lerMovimento    (validação: faixa, ausência)
MPU6050 ───────┘            │
                            ▼
                    gravarAmostra  → janela deslizante (20 s demo / 60 s projeto)
                            │
                  a cada PASSO_AVALIACAO_MS
                            ▼
                    coberturaFc / coberturaMov / mediaFc / movimentoPredominante
                            │
                            ▼
                    avaliarRegra  → histerese (100 entra / 92 sai) + persistência (2 avaliações)
                            │ só se o estado MUDOU
                            ▼
                    transitarPara → atualizarAtuacao (LED, buzzer)   ← efeito LOCAL
                            │
                            ▼
                    emitirEvento  → JSON com schemaVersion, eventId, sequence, reason
                            │
                            ▼
                    publicar ──▶ mqtt.publish OK? ──sim──▶ broker ──▶ consumidor
                                       │
                                       não
                                       ▼
                                  enfileirar (fila circular, 12 posições)
                                       │ na reconexão
                                       ▼
                                  esvaziarFila (em ordem)

consumidor: on_message → json.loads → validar (campos, versão, duplicata)
            → checar sequence (salto / inversão) → atualizar painel → alerta se ATENCAO
```

Três coisas para deixar claras:

1. **A decisão é local.** O ESP32 decide `NORMAL`/`ATENCAO` sozinho. A rede
   só leva a decisão para fora. Isso vem da Atividade 02 (decidir na borda).
2. **Só a transição é publicada.** Não publicamos telemetria a cada
   amostra — isso vira ruído no broker e gasta banda de um dispositivo
   restrito. (Decisão de *descartar* na comparação dos protótipos.)
3. **O consumidor não confia no transporte.** Ele revalida tudo:
   versão, campos, duplicata, ordem.

---

## 5. O contrato

```json
{
  "schemaVersion": 1,
  "eventType": "vitals.state.changed",
  "eventId": "esp32-borda-01-3",
  "deviceId": "esp32-borda-01",
  "entityId": "patient-0042",
  "eventTimeMs": 76082,
  "sequence": 3,
  "value": 132.5,
  "unit": "bpm",
  "state": "ATENCAO",
  "motion": "REST",
  "coverageFc": 1.00,
  "coverageMov": 1.00,
  "reason": "condicao_persistiu"
}
```

| Campo | Pergunta que responde | Por que existe |
|---|---|---|
| `schemaVersion` | como interpretar? | permite evoluir o formato; o consumidor rejeita versão que não entende em vez de ler pela metade |
| `eventType` | o que aconteceu? | um tópico pode carregar mais de um tipo no futuro |
| `eventId` | já vi este? | **deduplicação** — é `deviceId-sequence`, único por dispositivo |
| `deviceId` | quem produziu? | identidade do produtor |
| `entityId` | sobre quem? | a pessoa observada, pseudonimizada |
| `eventTimeMs` | quando? | `millis()` — **não é UTC**. Limitação declarada |
| `sequence` | em que ordem? | revela **salto** (perda), **repetição** e **inversão** — o transporte não conta isso |
| `value` / `unit` | qual a medida? | FC média da janela; `null` quando não há amostra válida |
| `state` | qual a decisão? | o que o consumidor mostra |
| `motion` | contexto | FC alta em repouso ≠ FC alta em atividade |
| `coverageFc` / `coverageMov` | quão confiável? | fração da janela com leitura válida |
| `reason` | por quê? | log explicável: `condicao_persistiu`, `cobertura_insuficiente`, `condicao_cessou`, `janela_com_cobertura` |

**Obrigatórios vs opcionais.** O consumidor exige os 7 primeiros (sem eles não
dá para identificar, ordenar ou interpretar). Os outros enriquecem o painel;
faltar um não invalida o evento. Isso permite que um produtor futuro omita
uma medida sem forçar nova versão.

**Versionamento.** Campo novo opcional → mesma versão. Campo removido,
renomeado ou com significado alterado → incrementa. O consumidor tem
`SCHEMA_SUPORTADO = 1` e rejeita explicitamente qualquer outra coisa.

**O que falta em relação ao slide do professor:** `correlationId`. Não temos
porque não há **comando** neste fluxo — só telemetria. Correlação liga um
comando à sua resposta; sem comando, não há o que correlacionar.

---

## 6. Falha

### 6.1 Broker indisponível (a condição exercitada)

O que acontece dentro do produtor quando `mqtt.publish()` falha:

1. `publicar()` chama `enfileirar()` — fila circular de 12 posições. Se
   encher, descarta o **mais antigo** (política: o estado presente importa
   mais que o histórico remoto).
2. O loop continua: amostragem, avaliação, transição, LED, buzzer. **Nada
   disso depende de rede.**
3. `conectarMqtt()` tenta reconectar a cada 3 s, sem bloquear.
4. Ao reconectar: publica `online` e chama `esvaziarFila()` — reenvia na
   ordem em que foram gerados, e para no primeiro que falhar.

No consumidor: os eventos chegam atrasados mas com `sequence` contínuo. Sem
aviso de salto. **A desconexão interrompeu a entrega, não a decisão.**

Como demonstrar: botão vermelho "falha broker" (GPIO 13) → `mqtt.disconnect()`
e bloqueio de reconexão. Mesmo efeito de o broker sumir, do ponto de vista do
código do produtor.

### 6.2 Silêncio do dispositivo (segunda condição)

Simulação interrompida sem encerramento → broker espera 1,5 × keepalive →
publica o *last will* → consumidor mostra `DISPOSITIVO offline`.

### 6.3 Perda, duplicata e inversão (tratadas no consumidor)

```python
if seq < ultima_sequencia:          → "fora de ordem"
elif seq > ultima_sequencia + 1:    → "salto: N evento(s) não recebido(s)"
if eventId in ids_processados:      → "duplicado", descartado
```

O consumidor não conserta nada — ele **torna visível**. Isso já é muito: o
transporte MQTT com QoS 0 não informa perda nenhuma.

### 6.4 As quatro dimensões de acoplamento (slide da aula)

| Dimensão | Pergunta | Nossa resposta |
|---|---|---|
| Espaço | o produtor conhece o endereço do consumidor? | **Não.** Conhece o broker e o tópico |
| Tempo | os dois precisam estar no ar ao mesmo tempo? | Parcialmente: sem *persistent session*, evento publicado sem assinante se perde. A fila protege do broker fora, não do consumidor fora |
| Contrato | mudar um campo quebra? | Campo novo opcional não quebra. Mudança incompatível é sinalizada por `schemaVersion` |
| Falha | um componente parado paralisa o outro? | **Não.** Produtor decide e atua sem rede; consumidor só reporta silêncio |

A linha "Tempo" é uma limitação honesta que vale declarar antes de perguntarem.

---

## 7. Por que MQTT e não HTTP

| Critério | MQTT (escolhido) | HTTP |
|---|---|---|
| Múltiplos consumidores | natural: assinaturas | cada um precisa de endpoint próprio ou de um intermediário |
| Quem conhece quem | produtor conhece só o tópico | produtor precisa do endereço do serviço |
| Dispositivo restrito | protocolo leve, conexão persistente | uma conexão por requisição, cabeçalhos maiores |
| Silêncio observável | *last will* | nada nativo; o servidor teria que inferir por timeout |
| Retry | o cliente MQTT já reconecta | o dispositivo implementa retry, backoff, idempotência |

HTTP **continua adequado** para outra coisa: consulta explícita ("qual o
estado agora?") e **comando** ("silencie o alarme"). Aí requisição/resposta,
status code e idempotência fazem sentido. Não é o caso deste fluxo.

Se perguntarem sobre gRPC ou Kafka: resolvem problemas que não temos —
chamadas tipadas entre serviços e stream durável com replay. "Comece pelo
requisito; use o menor mecanismo que o atenda."

---

## 8. Telemetria × comando

Nosso evento é **telemetria**: "o que foi observado". Pode ser frequente,
tolera alguma perda, tem validade temporal, alimenta estado e histórico.

Um **comando** ("ligue o alarme do cuidador") seria diferente: produz
consequência, pode exigir autorização, repetição pode ser perigosa,
confirmação precisa ter significado, pode expirar.

Por isso o protótipo de decisão e atuação (Murilo) **não** entrou nesta
fronteira: ele receberia um comando, e comando exige `correlationId`,
idempotência e confirmação de negócio, que ainda não definimos. Está em
`docs/comparacao.md` como próximo passo.

---

## 9. Onde está o estado e quem é responsável

| Estado | Onde vive | Quem responde |
|---|---|---|
| Janelas de FC e movimento | `fcAmostras[]`, `movAmostras[]` no ESP32 | produtor |
| Estado do paciente | `estadoAtual` no ESP32 | produtor (decide) |
| Fila de eventos pendentes | `fila[][]` no ESP32 | produtor |
| Contador de sequência | `sequenceEvento` no ESP32 | produtor |
| Conexões e assinaturas | broker | middleware |
| Última mensagem retida de `status` | broker | middleware |
| Cópia do estado para exibição | `estado_atual` no Python | consumidor (exibe) |
| IDs já processados, última sequência | `ids_processados`, `ultima_sequencia` no Python | consumidor |

Responsabilidades do grupo em `docs/decisoes.md` §6.

---

## 10. A "pequena alteração" — candidatos e onde

| Se pedirem... | Mexa em | Efeito visível |
|---|---|---|
| alertar com FC mais baixa | `FC_LIMIAR_ENTRADA` (sketch) | `ATENCAO` entra antes |
| exigir mais tempo para alertar | `AVALIACOES_PARA_ENTRAR` ou `TEMPO_MINIMO_ESTADO_MS` | mais avaliações até `ATENCAO` |
| aceitar janela menos preenchida | `COBERTURA_MINIMA` | sai de `DADOS_INSUFICIENTES` antes |
| fila maior/menor | `FILA_TAMANHO` | mais/menos eventos sobrevivem à desconexão |
| rejeitar o evento por versão | `SCHEMA_VERSION` no sketch **ou** `SCHEMA_SUPORTADO` no Python | consumidor imprime `REJEITADO schemaVersion 2 nao suportado` |
| tornar `reason` obrigatório | `CAMPOS_OBRIGATORIOS` no Python | nada muda (o produtor já envia); prova que a validação existe |
| mudar o alerta do consumidor | bloco `if estado_atual == "ATENCAO"` em `on_message` | texto/cor do alerta |
| novo campo no evento | `emitirEvento()` no sketch + tabela em `contrato/README.md` | consumidor continua aceitando (campo opcional) |

Regra prática: mudança no **produtor** exige reiniciar a simulação no Wokwi
(~1 min até chegar ao estado). Mudança no **consumidor** é `Ctrl+C` e rodar
de novo (segundos). Se puderem escolher, mostrem a alteração no consumidor.

---

## 11. Roteiro da demonstração

1. **Consumidor primeiro.** `python consumidor.py` → `aguardando eventos...`
2. **Produtor.** Iniciar simulação. Serial: `WiFi conectado`, `mqtt: conectado`.
   Consumidor: `dispositivo: ONLINE`.
3. **Estado inicial.** Aguardar `DADOS_INSUFICIENTES` (janela vazia) →
   `NORMAL` (janela cheia). Apontar `seq=1`, `seq=2`, `reason`.
4. **Alerta.** Potenciômetro acima de 100 bpm, MPU em repouso (Z = 1 g).
   Duas avaliações depois: `ATENCAO`, LED vermelho, buzzer, consumidor
   mostra `>>> ALERTA AO CUIDADOR`.
5. **Falha.** Clicar "falha broker". Serial: `FALHA SIMULADA`, `mqtt=OFF`.
   Baixar o potenciômetro. Serial: `NORMAL`, `evento enfileirado (1 na fila)`.
   LED verde. Consumidor: nada.
6. **Recuperação.** Clicar de novo. Serial: `mqtt: conectado`,
   `fila: reenviado (0 restantes)`. Consumidor: evento chega, `seq` contínuo.
7. **Silêncio.** Parar a simulação. Até 60 s depois: consumidor mostra
   `OFFLINE (last will)`.
8. **Encerrar** o consumidor com `Ctrl+C` (encerra limpo).

Tempo total: 4–5 min a ~30% de velocidade. Ter o consumidor e o Wokwi lado
a lado na tela.

---

## 12. Limitações a declarar (antes que perguntem)

- `eventTimeMs` é `millis()`, não UTC. Sem relógio, não há *watermark* nem
  política de evento tardio.
- Broker público, sem autenticação nem TLS. Qualquer um que saiba o tópico
  lê e publica. Uma versão real exigiria credenciais, autorização por tópico
  e canal cifrado.
- Sem *persistent session*: consumidor fora do ar perde eventos. A fila
  protege do broker fora, não do consumidor fora.
- Fila em RAM, 12 posições. Reinício do ESP32 zera a fila e o `sequence`.
- FC é potenciômetro. Nada tem valor clínico.
- A simulação roda a 30% do tempo real; o keepalive precisou ser ajustado
  por isso. Timing do Wokwi não valida timing do mundo.

---

## 13. Perguntas prováveis — respostas curtas

**"Qual é o protocolo e qual é o middleware?"**
MQTT é o protocolo. O broker HiveMQ é o middleware.

**"O que o broker faz?"**
Aceita conexões, guarda quem assinou o quê, roteia cada publicação para os
assinantes do tópico, mantém a sessão viva com PING, guarda a última
mensagem retida e publica o *last will* quando a conexão cai.

**"Por que o produtor não fala direto com o consumidor?"**
Porque na Atividade 02 a telemetria tem mais de um destino. Com o broker, o
produtor não precisa conhecer nenhum deles.

**"Como você sabe que o evento chegou?"**
Não sei pelo transporte (QoS 0). Sei pelo consumidor: ele exibe, e checa
`sequence` — se pulou, algum não chegou.

**"E se chegar duas vezes?"**
`eventId` já está em `ids_processados` → descartado, contado em
`descartados`.

**"E se chegar fora de ordem?"**
`seq < ultima_sequencia` → aviso. O consumidor não reordena; sinaliza.

**"O que acontece se o broker cair?"**
O produtor continua decidindo e atuando; os eventos vão para a fila; ao
reconectar, reenvia em ordem. A desconexão interrompe a entrega, não a
decisão.

**"E se o consumidor cair?"**
O produtor nem percebe. Os eventos publicados nesse intervalo se perdem
(sem *persistent session*). Quando o consumidor voltar, o próximo evento
mostra salto na sequência. Limitação conhecida.

**"Por que QoS 0?"**
Evento raro, com identidade e sequência próprias, e fila própria para a
falha que importa. QoS 1 só acrescentaria duplicatas que o `eventId` já
trata. E QoS não garante processamento, só entrega.

**"Por que versionar o contrato?"**
Para que uma mudança de campo não quebre o consumidor em silêncio. Ele
rejeita o que não entende em vez de interpretar pela metade.

**"Por que `eventTimeMs` e não uma data?"**
ESP32 sem NTP. Declaramos a limitação em vez de mandar uma data falsa.

**"Isso é telemetria ou comando?"**
Telemetria. Comando exigiria autorização, idempotência e confirmação de
negócio — próxima fronteira.

**"O que preservaram dos protótipos?"**
Janela deslizante, cobertura mínima, persistência e `reason` (Matheus);
histerese com limiares distintos e distinção alerta/falha de sensor
(Murilo). Adaptado: `schemaVersion`. Descartado: publicar a cada amostra.

**"O que não foi integrado?"**
BLE, Android, nuvem, histórico, watermark. O Marco 2 pede **uma** fronteira.

**"Onde está o estado do paciente?"**
No ESP32, em `estadoAtual`. O consumidor tem uma cópia para exibir. O broker
não tem estado de negócio.

**"Mude X agora."**
Ver §10. Preferir alterações no consumidor (reinício em segundos).
