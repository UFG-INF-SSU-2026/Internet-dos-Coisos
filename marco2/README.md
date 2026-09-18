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

1. Abra um projeto ESP32 no Wokwi.
2. Cole `produtor/diagram.json` na aba do diagrama e `produtor/sketch.ino` na aba do código.
3. Adicione as bibliotecas de `produtor/libraries.txt` (PubSubClient, Adafruit MPU6050, Adafruit Unified Sensor, Adafruit BusIO).
4. Inicie a simulação.

O monitor serial deve mostrar `WiFi conectado` e `mqtt: conectado`.

### 3. Provocar a mudança de estado

- MPU6050: X = 0, Y = 0, Z = 1 g (repouso).
- Potenciômetro: acima de 100 bpm.
- Aguarde a janela encher. O consumidor recebe `NORMAL` e depois `ATENCAO`.

> **Tópico compartilhado.** O broker é público, então o prefixo `ufg/ssu/2026-2/internet-das-coisos` identifica o grupo e evita receber publicações de terceiros. Ele precisa ser idêntico em `sketch.ino` e `consumidor.py`.

---

## Condição de falha exercitada

**Broker indisponível.**

Para demonstrar: com a integração funcionando, desconecte a rede da máquina ou pare o consumidor e observe o produtor. O monitor serial passa a mostrar:

```
mqtt: INDISPONIVEL - evento enfileirado (n na fila)
```

O produtor **continua amostrando, avaliando a janela e transitando de estado**. O LED e o buzzer seguem funcionando. Ao reconectar, a fila é esvaziada em ordem:

```
fila: reenviado (2 restantes)
```

A desconexão interrompe a entrega, não a decisão.

Há ainda um segundo mecanismo: o produtor declara *last will* no tópico `.../status`. Se a simulação for interrompida sem encerramento, o próprio broker publica `offline` e o consumidor mostra que o dispositivo ficou silencioso. Ausência de dado não é ausência de risco.

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
