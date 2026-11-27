# Marcos 3 e 4 — Registro de decisões

Os requisitos gerais do Marco 3 foram passados por e-mail e os detalhes foram conversados em aula.
Este arquivo registra **o que perguntamos, o que foi respondido e o que decidimos**, com o motivo.

## Requisitos do professor

1. Evoluir a arquitetura produtor-consumidor do Marco 2.
2. Segurança no canal de comunicação.
3. Identificação e autenticação dos dispositivos.
4. Autorização das mensagens/publicações.
5. Pelo menos um novo ciclo produtor-consumidor, de preferência com o antigo consumidor como novo produtor.
6. Demonstração na bancada, com explicação da implementação (10 min).

Orientação adicional: todos do grupo devem entender a solução de ponta a ponta; uma solução mais simples e bem explicada é preferível.

## Perguntas esclarecidas

| Pergunta | Resposta |
|---|---|
| Precisamos manter MQTT junto com HTTP? | Opcional. |
| Qual o intervalo de *polling* do ESP32 para buscar comandos? | A critério do grupo. |
| Uma única chave por dispositivo basta para autenticação? | Sim. |

## Decisões

| # | Decisão | Motivo |
|---|---|---|
| D1 | Só HTTP/REST, sem MQTT | MQTT é opcional. Uma tecnologia a menos para configurar e explicar; REST deixa explícitos os códigos 401 (não autenticado) e 403 (não autorizado). |
| D2 | Sessão do cuidador com cookie `SameSite=Lax` e sem token CSRF dedicado | Suficiente como escolha didática para o protótipo, **não** proteção equivalente a CSRF completo em produção. |
| D3 | Sem heartbeat separado | A consulta de comando a cada 3 s já atualiza o "último contato" do ESP32. |
| D4 | Descarte de `loteId` repetido + ordem FIFO de recebimento | Lotes duplicados recentes não são reprocessados; o consumidor processa mensagens válidas na ordem da fila em um único processo. |
| D5 | A análise (janela, cobertura, histerese, persistência) saiu do ESP32 e foi para `api/regra.py` | Menos código em C. Em Python a regra é testada sem simulador (`test_regra.py`) e é mais fácil de explicar e alterar. A regra é a mesma do Marco 2. |
| D6 | Um comando por vez, um tipo (`RECONHECER_ALERTA`), 3 status | Um paciente, um dispositivo, uma ação. `PENDENTE → ENTREGUE → EXECUTADO`. |
| D7 | Regra local mínima no ESP32, só quando a API não responde por 8 s | Sem rede o paciente ainda é alertado (FC > 100 bpm em repouso), sem duplicar a análise completa. |
| D8 | Ciclo 2 com rotas próprias | Baixo acoplamento: o ciclo 1 não depende do ciclo 2, e o novo ciclo fica visível na demonstração. |
| D9 | Lote de 3 leituras a cada 3 s | Menos requisições do que uma por leitura e resposta rápida para a demo de 5 min. |
| D10 | *Polling* de comando a cada 3 s | O ESP32 não tem endereço público para a API "empurrar" o comando; 3 s deixa o ciclo 2 visível em poucos segundos. |
| D15 | Tempos curtos para a demo: janela de 10 leituras (FC) e 5 (movimento), 4 s mínimos em cada estado, 8 s sem lote = `DADOS_INSUFICIENTES` | A demonstração tem 5 min; cada mudança de estado aparece em ~9 s. O projeto original usava janela de 120 s. |
| D17 | Comunicação HTTP assinada por HMAC-SHA256 + horário | O grupo relatou falha TLS no **sketch original**, então manteve HTTP com HMAC para dados **sintéticos**. A janela de 120 s rejeita assinaturas antigas, mas não impede todos os replays dentro da janela. **Não há confidencialidade** e a solução não serve para dados reais. |
| D16 | Janela contada em **leituras**, não em horário de chegada; silêncio verificado à parte | Atrasos de rede no Wokwi (alguns segundos por requisição) não fazem o estado piscar; a queda real é detectada pelos 8 s sem lote. |
| D11 | Uma chave privada por dispositivo, gerada localmente | Consolidação da branch `marco3-enxuto`: `gerar_config.py` gera `api/.env` e `produtor/config.h` com chave consistente, ambos ignorados pelo Git. Não publicar a chave no Wokwi público. A senha do cuidador é armazenada somente como hash no `.env`. |
| D12 | Sem fila offline no ESP32 | Lote que falha é descartado; a API percebe a falta de leituras e mostra `DADOS_INSUFICIENTES`. Preferimos mostrar a falta de dados a mostrar dados atrasados como atuais. Um broker não resolveria: com a rede do ESP32 fora, a leitura não sai do dispositivo. |
| D13 | Estado operacional, fila e comando pendente em memória | Versão original não tinha banco. **Revisto em D20:** os eventos históricos podem ser persistidos; reiniciar a API ainda reinicia a sessão, o estado corrente e a fila. |
| D14 | Reconhecer o alerta só silencia o buzzer | O LED continua aceso e o estado não muda: o cuidador ter visto não significa que o risco passou. Só a regra encerra o alerta. |

## Quem produz e quem consome

| Ciclo | Produtor | Mensagem | Consumidor |
|---|---|---|---|
| 1 | ESP32 | lote de leituras | API (decide o estado) → painel do cuidador |
| 2 | Cuidador (painel) | comando `RECONHECER_ALERTA` | ESP32 |
| 2 | ESP32 | confirmação (ack) | API → painel do cuidador |

No Marco 2 o cuidador só consumia. No Marco 3 ele também produz, e o ESP32 também consome.

## Segurança: o que cada mecanismo garante

| Pergunta | Mecanismo |
|---|---|
| Alguém no meio do caminho altera, forja ou repete mensagens? (**canal**) | Não: cada mensagem do ESP32 leva `HMAC-SHA256(chave, horário + método + rota + corpo)`. Alterar um byte invalida a assinatura; sem a chave não se assina; mensagem com mais de 120 s é recusada. **Ler** as leituras no caminho é possível (sem HTTPS no Wokwi, D17). |
| Quem está falando? (**autenticação**) | ESP32: assinatura que só quem tem a chave consegue gerar (a chave não trafega). Cuidador: usuário e senha (hash scrypt com salt) e depois cookie de sessão assinado. |
| Pode fazer isso? (**autorização**) | A API confere os vínculos `esp32-borda-01 → patient-0042 → cuidador01`. Dispositivo errado: 403. Outro paciente: 403. ESP32 não cria comando; cuidador não forja ack. |

## Limitações assumidas

- Sem HTTPS (limitação do Wokwi, D17): as leituras podem ser lidas no caminho.
- A URL do túnel gratuito muda a cada reinício do `cloudflared`.
- Sinais simulados; sem valor clínico.
- TimescaleDB é necessário para comprovar persistência; sem ele, a API funciona só em memória. Não há múltiplos pacientes nem limitação de tentativas de login.


## Revisão após feedback do professor — entrega consolidada

**Estas decisões atualizam as limitações históricas D13 e a visão do Marco 3 original.**

| ID | Melhoria | Decisão/justificativa |
|---|---|---|
| D18 | WebSocket | Push de eventos API → painel com sessão autenticada; a comunicação ESP32 → API continua HTTP/HMAC. O REST permanece para consulta e contingência. |
| D19 | Fila FIFO | `asyncio.Queue(maxsize=128)` com consumidor único, entre recebimento HTTP e regra.py. Em memória, sem durabilidade após reiniciar. Não é fila offline no ESP32 (mantém D12). |
| D20 | TimescaleDB | Código consolidado da branch `timescaledb`: `armazenamento.py` cria três hypertables por `ts`: `leituras`, `eventos_estado`, `comandos`. A fila e o comando **pendente** permanecem na memória, mas suas ocorrências e mudanças de status são gravadas no banco quando disponível. A extensão e as hypertables são verificáveis pelo script `verificar_banco.py`. |
| D21 | Simulação | Cenários `0`,`1`,`2`,`3`,`4`,`a`,`f` acionados pelo Serial Monitor; representação totalmente sintética e de ensino. |
| D22 | Verificabilidade | Endpoint `/api/saude`, testes Python e scripts para confirmar fluxo sem Wokwi e hypertable real; os dois últimos não substituem o teste integral do simulador. |

**Correção de segurança de D17:** o Wokwi suporta HTTPS em geral. O projeto específico teve dificuldade no handshake TLS e, por isso, utiliza HTTP com HMAC. HMAC garante autenticidade/integridade, **não confidencialidade**. O timestamp rejeita assinaturas fora da janela de 120 segundos, mas **um atacante ainda pode repetir mensagens dentro da janela**; a deduplicação por `loteId` reduz reprocessamentos recentes de lotes. A chave deixou de ser versionada na consolidação da branch `marco3-enxuto`.

**Nota sobre streaming:** o ESP32 gera leituras continuamente e envia lotes; a API mantém uma fila assíncrona e envia estados pelo WebSocket. Isto não é Kafka, RabbitMQ ou exatamente-once delivery. Um único worker FastAPI deve ser usado para preservar fila e estado.


## Marco 4: app Android como segundo produtor

| ID | Decisão | Motivo e consequência |
|---|---|---|
| D23 | App Android nativo em Kotlin + Jetpack Compose, sem bibliotecas de rede extras (`HttpURLConnection` + `org.json`) | O enunciado exige app instalável (página web/PWA não vale). Menos dependências para o Gradle baixar e para o grupo explicar. |
| D24 | Login do app gera um token Bearer assinado com `APP_SECRET_KEY` (itsdangerous), com usuário e paciente, válido por 8 h | Nenhuma chave dentro do APK, e o servidor não guarda sessão para o app. **Consequência:** um token não pode ser revogado antes de vencer, a não ser trocando `APP_SECRET_KEY`, o que derruba todos os tokens. |
| D25 | O app consulta o estado a cada 2 s em vez de usar o WebSocket do painel | Mais simples de implementar e testar no prazo; 2 s é suficiente diante das janelas de 10 s da regra. O painel web continua com WebSocket (D18). |
| D26 | O acelerômetro do celular é o segundo produtor: envia a cada 2 s o pico de \|a/9,81 − 1\| (em g) desde o último envio | Usa um sensor do celular com função no cenário. O pico, e não a média, não deixa uma sacudida curta se perder. O limiar é o mesmo do MPU6050: até 0,15 g é repouso. |
| D27 | Mudança de contexto: movimento `ACTIVE` vindo do celular nos últimos 6 s prevalece sobre o MPU6050 | Paciente em movimento não gera alerta de FC alta (a FC sobe com esforço). Só o `ACTIVE` sobrescreve: o celular parado não anula movimento detectado pelo ESP32. Depois de 6 s sem leitura do celular, o contexto expira e vale de novo só o ESP32. A transição causada pelo celular fica registrada como `razao = movimento_no_celular`. A leitura do celular **não conta** para a persistência de entrada (o alerta continua exigindo 2 lotes do ESP32) e não reavalia a janela quando o ESP32 está em silêncio (correção `a94e70b`, encontrada na avaliação). |
| D28 | Validade da leitura do celular: atrasada há mais de 10 s, adiantada mais de 5 s ou mais antiga que a última aceita recebe 422 e não entra na fila | Leitura velha não pode mudar o contexto atual. O tempo usado é o de captura (`capturadoEmMs`), não o de chegada. As descartadas são contadas em `celular.descartadas`. |
| D29 | As leituras do celular entram na mesma fila FIFO do ESP32, com consumidor único | Dois produtores e uma ordem única de processamento, sem trava. A resposta HTTP espera o processamento, como no ciclo 1. |
| D30 | O app só usa HTTPS (`usesCleartextTraffic=false`), e o Android valida o certificado do túnel | Canal protegido com validação da identidade do serviço, como pede o enunciado. O ESP32 continua com HTTP + HMAC (D17), uma limitação declarada. |
| D31 | As leituras do celular não são gravadas no TimescaleDB; só as transições que elas causam | O valor do movimento não é usado depois da janela de 6 s. A transição com `movimento_no_celular` em `eventos_estado` já comprova o efeito do contexto. |
| D32 | O limite de silêncio acompanha o ritmo dos lotes: 2,5 × a mediana dos últimos 5 intervalos, entre 8 s e 30 s | Achado do ensaio no Wokwi: o simulador roda a ~40% da velocidade real, e os lotes de 3 s chegavam a cada 7–10 s de relógio. Com o silêncio fixo de 8 s, o estado alternava `ATENCAO`/`NORMAL`/`DADOS_INSUFICIENTES`. Com o ESP32 a cada 3 s, o limite continua 8 s. O teto de 30 s garante que uma queda real continue detectada; a mediana impede que uma queda isolada estique o limite. |
| D33 | No ensaio, o ESP32 fala com a API pelo gateway local do Wokwi no VS Code (`http://host.wokwi.internal:5000`), e não pelo túnel | Em 27/11/2026 o túnel rápido da Cloudflare passou a responder `301` para todo `http://`, redirecionando para HTTPS, e o sketch descarta o lote (D17). Pelo gateway local, o tráfego do ESP32 não sai da máquina, o que também tira da internet o trecho sem sigilo. O app continua pelo túnel HTTPS (D30). No wokwi.com, sem gateway local, o ESP32 precisaria de HTTPS. |
| D34 | A FC é medida pelo ESP32 numa onda de pulso (PPG) simulada por um chip próprio do Wokwi (`produtor/sensor-pulso.chip.c`); o potenciômetro passou a definir o ritmo do coração simulado | Sugestão do professor: nenhum sensor cardíaco real entrega a FC como uma tensão proporcional. Um sensor óptico entrega a onda, e o dispositivo detecta os batimentos (50 Hz, envoltória adaptativa, refratário de 300 ms, FC = 60 / mediana dos últimos 5 intervalos, inválida após 3 s sem batimento). Os cenários agora só mexem no coração simulado (ritmo 78/135 bpm, dedo fora, artefato de movimento), e a FC sempre passa pela detecção. O artefato de movimento faz a FC medida errar, o problema real que o contexto de atividade trata. O ritmo dos cenários usa dois pinos digitais (R0/R1), porque o Wokwi não simula o DAC do ESP32. A API e a regra não mudaram. |

### Quem produz e quem consome no Marco 4

| Ciclo | Produtor | Mensagem | Consumidor |
|---|---|---|---|
| 1 | ESP32 | lote de leituras (FC, g) | API → fila → regra → painel e app |
| 1 | **App Android** | **intensidade do movimento** | **API → mesma fila → regra (contexto)** |
| 2 | Cuidador (painel **ou app**) | comando `RECONHECER_ALERTA` | ESP32 |
| 2 | ESP32 | ACK | API → painel e app |
