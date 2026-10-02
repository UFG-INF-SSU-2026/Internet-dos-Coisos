# Marco 2 — Integração produtor / consumidor

**Software para Sistemas Ubíquos — UFG / Instituto de Informática**
Grupo **Internet das Coisos**: Felipe Alves Leão de Araújo, Felipe O Carvalho, Matheus Augusto Ferreira Medeiros, Murilo Bernardo

Projeto: monitoramento de sinais vitais de pessoas em situação de vulnerabilidade física por meio de *smart clothing*.

---

## A fronteira integrada

```
ESP32 / Wokwi  ──MQTT──▶  broker  ──▶  serviço consumidor (Python)
  (produtor)                                (consumidor)
```

O produtor é o protótipo individual do Marco 1 responsável por **estado e processamento temporal**: janela deslizante, cobertura mínima, histerese e persistência. Ele já decidia localmente; agora publica a decisão.

O consumidor valida o contrato, reconhece duplicata e perda pela sequência, e produz efeito observável: painel de estado e alerta ao cuidador.

Não integramos o sistema inteiro. Validamos uma fronteira real entre dois componentes, com uma condição de falha tratada.

---

## Estrutura

```
marco2/
├── produtor/       sketch.ino, diagram.json, libraries.txt
├── consumidor/     consumidor.py, requirements.txt
├── contrato/       evento-v1.json e descrição dos campos
└── docs/           arquitetura-visual.svg, arquitetura.svg, arquitetura.mmd,
                    decisoes.md, comparacao.md,
                    proposta-marco-2.pdf (slides da Aula 05 com o enunciado)
```

---

## Como executar

### 1. Consumidor (primeiro)

```bash
cd consumidor
pip install -r requirements.txt
python consumidor.py
```

Deve aparecer `conectado a broker.hivemq.com` e `aguardando eventos...`.

### 2. Produtor

**Simulação pronta no Wokwi:** https://wokwi.com/projects/476807564770058241 — basta abrir e iniciar a simulação.

Para montar do zero:

1. Abra um projeto ESP32 no Wokwi.
2. Cole `produtor/diagram.json` na aba do diagrama e `produtor/sketch.ino` na aba do código.
3. Adicione as bibliotecas de `produtor/libraries.txt` (PubSubClient, Adafruit MPU6050, Adafruit Unified Sensor, Adafruit BusIO).
4. Inicie a simulação.

O monitor serial deve mostrar `WiFi conectado` e `mqtt: conectado`.

### 3. Provocar a mudança de estado

- MPU6050: X = 0, Y = 0, Z = 1 g (repouso).
- Potenciômetro: acima de 100 bpm.
- Aguarde a janela encher. O consumidor recebe, nesta ordem:
  1. `DESCONHECIDO → DADOS_INSUFICIENTES` (`sequence` 1, razão `cobertura_insuficiente`): na primeira avaliação a janela ainda está quase vazia;
  2. `DADOS_INSUFICIENTES → NORMAL` (razão `janela_com_cobertura`): a cobertura passou de 70% e ainda não houve persistência;
  3. `NORMAL → ATENCAO` (razão `condicao_persistiu`): FC média acima de 100 bpm em repouso por 2 avaliações seguidas e pelo menos 10 s em `NORMAL`.

> **Tópico compartilhado.** O broker é público, então o prefixo `ufg/ssu/2026-2/internet-das-coisos` identifica o grupo e evita receber publicações de terceiros. Ele precisa ser idêntico em `sketch.ino` e `consumidor.py`.

---

## Caminho do dado: o que fica em cada lado

### Fluxo

```
PRODUTOR (ESP32)                                       BROKER            CONSUMIDOR (Python)
─────────────────────────────────────────────────      ──────────        ───────────────────
potenciômetro ─┐
               ├─▶ leitura + validação (1/s)
MPU6050 ───────┘     OK | FORA_DE_FAIXA | AUSENTE
                         │
                         ▼
               janela circular (FC 20 s, MOV 10 s)
                         │  a cada 5 s
                         ▼
               cobertura ≥ 70%? ──não──▶ DADOS_INSUFICIENTES
                         │ sim
                         ▼
               regra + histerese + persistência
                         │  só quando o estado MUDA
                         ▼
               LED / buzzer  +  evento JSON (sequence++)
                         │
               publish ok? ──sim───────────────▶  .../state  ──▶  valida → dedup → sequence
                         │ não                                       → painel / alerta
                         ▼
               fila local (12 eventos) ──reconexão──▶ .../state
```

Amostra bruta **nunca sai do ESP32**. O que atravessa a fronteira é só o evento de mudança de estado, com a média e as coberturas que justificaram a decisão. Se nada muda, nada é publicado.

### Dados suficientes (cobertura)

Fica **no produtor**, antes da regra. A cada segundo cada leitura entra na janela marcada como válida ou não:

| Leitura inválida quando | FC | Movimento |
|---|---|---|
| botão "silenciar" pressionado | `AUSENTE` | `INVALIDO` |
| fora da faixa plausível | < 30 ou > 220 bpm | > 8 g |
| sensor não respondeu | — | MPU ausente ou falha de leitura |

Na avaliação, cobertura = posições válidas ÷ tamanho da janela. As **duas** precisam ser ≥ `COBERTURA_MINIMA` (0,70): no modo demo, 14 de 20 amostras de FC e 7 de 10 de movimento. A média de FC usa só as válidas.

- Abaixo do mínimo, o estado vai para `DADOS_INSUFICIENTES` **imediatamente** (sem tempo mínimo no estado) e a contagem de persistência zera. LED azul.
- O buzzer **não** é desligado nessa transição: se o paciente estava em `ATENCAO`, o alerta continua. Perder o sensor não prova que o risco passou; só `NORMAL` desliga o alerta.
- Ao ligar, a janela começa vazia, então a primeira avaliação emite `DESCONHECIDO → DADOS_INSUFICIENTES` (`sequence` 1). O estado só sai daí quando a janela acumula leituras válidas suficientes; por isso é preciso "aguardar a janela encher" antes de ver `NORMAL`.
- O consumidor não recalcula cobertura. Ele recebe `coverageFc`/`coverageMov` no evento e apenas os exibe.

### Fila

Fica **no produtor**, porque é lá que a decisão é tomada e lá que o evento nasce. `publicar()` tenta o `publish`; se o cliente estiver desconectado, o `publish` falhar ou a falha simulada estiver ativa, o JSON pronto vai para a fila.

- Buffer circular de `FILA_TAMANHO` = 12 eventos × 320 bytes (~3,8 KB de RAM).
- Guarda **eventos**, não amostras: 12 transições de estado, não 12 segundos.
- Cheia, descarta o **mais antigo**. O consumidor percebe a perda pelo salto de `sequence` (`AVISO salto na sequencia`).
- É esvaziada em ordem (FIFO) na reconexão, ao encerrar a falha simulada e a cada volta do `loop` com o cliente conectado. Se um reenvio falhar, para e tenta de novo depois, sem pular nenhum.
- O evento reenviado é o mesmo JSON de quando foi gerado: `eventTimeMs` marca quando a decisão foi tomada, não quando chegou.

### Armazenamento

Ninguém grava em disco. Tudo é memória volátil:

| Onde | O que guarda | Perde quando |
|---|---|---|
| **Produtor** (RAM do ESP32) | janelas de FC e movimento, estado atual e desde quando, contador de persistência, `sequence`, fila | reinicia a simulação |
| **Broker** | apenas a última mensagem *retained* de `.../status` (`online`/`offline`) e o *last will* registrado. Eventos de `.../state` **não** ficam guardados (sem *retain*, QoS 0 na publicação) | — |
| **Consumidor** (memória do processo) | último `sequence`, conjunto de `eventId` já processados, estado e disponibilidade exibidos, contadores | o script é encerrado |

Consequências diretas:

- **Consumidor fora do ar:** o broker não segura os eventos de `state` para ele. Ao voltar, recebe imediatamente o `status` retido, mas as transições perdidas só aparecem como salto de `sequence` no próximo evento.
- **Produtor reiniciado com o consumidor rodando:** `sequence` volta a 1 e o `eventId` (`esp32-borda-01-<sequence>`) se repete. O consumidor rejeita esses eventos como `duplicado` até o `sequence` passar do último visto. Para uma demonstração limpa, reinicie também o consumidor. Uma versão real incluiria um identificador de inicialização (*boot id*) no `eventId`.
- `ids_processados` cresce sem limite enquanto o consumidor roda. Basta para a demonstração; uma versão real manteria só uma janela recente de identificadores ou persistiria o último `sequence` por dispositivo.

---

## Condição de falha exercitada

**Broker indisponível.**

Para demonstrar: com a integração funcionando, clique no botão vermelho **"falha broker"** (GPIO 13) no diagrama do Wokwi. A partir daí o produtor trata toda publicação como falha — exatamente o caminho que `publish()` seguiria com o broker fora do ar — até o próximo clique. Em seguida provoque uma transição (por exemplo, suba o potenciômetro acima de 100 bpm para entrar em `ATENCAO`). O monitor serial passa a mostrar:

```
FALHA SIMULADA: broker indisponivel - publicacoes vao para a fila
mqtt: INDISPONIVEL - evento enfileirado (1 na fila)
... mqtt=OFF fila=1
```

O produtor **continua amostrando, avaliando a janela e transitando de estado**. O LED e o buzzer seguem funcionando. O consumidor não recebe nada nesse intervalo. Clique no botão de novo: o produtor esvazia a fila em ordem:

```
falha simulada encerrada - broker disponivel, esvaziando fila
fila: reenviado (0 restantes)
```

No consumidor o evento chega com o `sequence` correto, sem salto. A desconexão interrompe a entrega, não a decisão.

Teclar `f` com o monitor serial em foco faz o mesmo que o botão.

> **Por que a simulação não derruba o socket.** A primeira versão do botão chamava `mqtt.disconnect()`. No Wokwi a reconexão seguinte falhou repetidamente (`rc=-2`, TCP `connect` recusado) e, pior, cada tentativa do `PubSubClient` bloqueou o loop por ~10 s — sem amostra, sem decisão. A simulação agora intercepta no `publish`, que é onde a falha real de rede também aparece para o código; o caminho de reconexão continua existindo para quedas reais (foi ele que reconectou o dispositivo quando o *keepalive* estourava). O bloqueio da reconexão síncrona é uma limitação conhecida da biblioteca; `RETENTATIVA_MQTT_MS` foi elevado a 15 s para que o loop respire entre tentativas.

> Parar o consumidor **não** exercita essa falha: o produtor continua conectado ao broker e publica normalmente; quem perde os eventos é o consumidor, que ao voltar verá um salto na sequência. Isso também é observável, mas é outra condição.

Há ainda um segundo mecanismo: o produtor declara *last will* no tópico `.../status`. Se a simulação for interrompida sem encerramento, o próprio broker publica `offline` (em até 60 s, 1,5× o *keepalive* declarado) e o consumidor mostra que o dispositivo ficou silencioso. Ausência de dado não é ausência de risco.

> **Keepalive no Wokwi.** A simulação com WiFi roda mais devagar que o tempo real, e com o *keepalive* padrão de 15 s o PING chegava atrasado: o broker derrubava a conexão a cada ~25 s e publicava `offline` sem que nada tivesse falhado. O produtor agora declara 40 s ao broker mas pinga a cada 10 s simulados (`MQTT_KEEPALIVE_BROKER_S` / `MQTT_KEEPALIVE_CLIENTE_S`). Se ainda aparecer `offline` espontâneo, é isso, não a fila.

---

## Decisões arquiteturais

Detalhadas em [`docs/decisoes.md`](docs/decisoes.md). Em resumo:

| Decisão | Escolha | Justificativa |
|---|---|---|
| Mecanismo | MQTT | múltiplos consumidores, desacoplamento espacial, dispositivo restrito |
| Contrato | JSON versionado (`schemaVersion`) | permite evoluir sem quebrar o consumidor |
| Identidade | `eventId` + `sequence` | deduplicação e detecção de perda ou inversão |
| Falha | fila local + reenvio em ordem | decisão local sobrevive à perda de rede |
| Silêncio | *last will* MQTT | torna a desconexão observável pelo consumidor |
| QoS | 0 no produtor, 1 no consumidor | evento de transição já tem fila própria e `sequence`; duplicata é tratada pelo `eventId` |

## Arquitetura

![Visão geral da integração](docs/arquitetura-visual.svg)

Visão detalhada, com as etapas internas de cada componente:

![Arquitetura da fronteira integrada](docs/arquitetura.svg)

Versão resumida em Mermaid: [`docs/arquitetura.mmd`](docs/arquitetura.mmd).

A comparação entre os protótipos individuais do Marco 1, com o que foi preservado, adaptado e descartado, está em [`docs/comparacao.md`](docs/comparacao.md).

---

## Limitações conhecidas

- `eventTimeMs` é `millis()`, não UTC. Sem relógio sincronizado, não há watermark nem política de eventos tardios.
- A entrada de frequência cardíaca é **substituta** (potenciômetro). Não há aquisição de sinal fisiológico real e nenhuma saída tem valor clínico.
- Broker público, sem autenticação nem TLS. Uma versão real exigiria credenciais, autorização por tópico e canal cifrado.
- BLE, aplicativo Android e histórico em nuvem permanecem fora desta fronteira.
- `mqtt.connect()` do `PubSubClient` é síncrono: com o broker fora do ar, cada tentativa de reconexão bloqueia o loop por até ~10 s. Entre tentativas (15 s) o produtor amostra e decide normalmente. Uma versão real usaria cliente assíncrono ou tarefa separada.

---

## Modo de demonstração

`MODO_DEMO 1` no início do `sketch.ino` reduz a janela para 20 s e o passo de avaliação para 5 s, para caber no tempo da apresentação. `MODO_DEMO 0` restaura os parâmetros da Atividade 02 (60 s e 15 s).

## Onde alterar na verificação

Todos os parâmetros ficam no bloco `1. CONFIGURACAO` do `sketch.ino` e no topo do `consumidor.py`:

| Alteração provável | Onde |
|---|---|
| limiar de entrada / saída em `ATENCAO` | `FC_LIMIAR_ENTRADA`, `FC_LIMIAR_SAIDA` |
| cobertura mínima da janela | `COBERTURA_MINIMA` |
| persistência antes de alertar | `AVALIACOES_PARA_ENTRAR`, `TEMPO_MINIMO_ESTADO_MS` |
| capacidade da fila offline | `FILA_TAMANHO` |
| rejeição por versão do contrato | `SCHEMA_VERSION` (produtor) ≠ `SCHEMA_SUPORTADO` (consumidor) |
| campo obrigatório no consumidor | `CAMPOS_OBRIGATORIOS` |
