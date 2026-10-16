# Marco 3 — Registro de decisões

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
| D2 | Login sem token CSRF; cookie de sessão `SameSite=Lax` | Com `Lax` o navegador não envia o cookie em POST vindo de outro site. Menos código com proteção equivalente para o protótipo. |
| D3 | Sem heartbeat separado | A consulta de comando a cada 5 s já atualiza o "último contato" do ESP32. |
| D4 | Sem controle de ordem; só descarte de lote repetido (`loteId`) | Cada lote é independente; a repetição (resposta perdida e reenvio) é o único caso que importa. |
| D5 | A análise (janela, cobertura, histerese, persistência) saiu do ESP32 e foi para `api/regra.py` | Menos código em C. Em Python a regra é testada sem simulador (`test_regra.py`) e é mais fácil de explicar e alterar. A regra é a mesma do Marco 2. |
| D6 | Um comando por vez, um tipo (`RECONHECER_ALERTA`), 3 status | Um paciente, um dispositivo, uma ação. `PENDENTE → ENTREGUE → EXECUTADO`. |
| D7 | Regra local mínima no ESP32, só quando a API não responde por 15 s | Sem rede o paciente ainda é alertado (FC > 100 bpm em repouso), sem duplicar a análise completa. |
| D8 | Ciclo 2 com rotas próprias | Baixo acoplamento: o ciclo 1 não depende do ciclo 2, e o novo ciclo fica visível na demonstração. |
| D9 | Lote de 5 leituras a cada 5 s | Menos conexões HTTPS (cada uma tem *handshake* TLS); atraso aceitável para a demo. |
| D10 | *Polling* de comando a cada 5 s | O ESP32 não tem endereço público para a API "empurrar" o comando; 5 s é rápido para a demo e não ocupa o laço o tempo todo. |
| D11 | Uma chave por dispositivo (`X-Device-Key`), gerada por `gerar_config.py` | Confirmado como suficiente. A chave nunca vai para o GitHub (`.gitignore`). |
| D12 | Sem fila offline no ESP32 | Lote que falha é descartado; a API percebe a falta de leituras e mostra `DADOS_INSUFICIENTES`. Preferimos mostrar a falta de dados a mostrar dados atrasados como atuais. Um broker não resolveria: com a rede do ESP32 fora, a leitura não sai do dispositivo. |
| D13 | Dados em memória, sem banco | Um paciente e um cuidador. Reiniciar a API apaga o histórico (limitação assumida). |
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
| Alguém no meio do caminho lê ou altera os dados? (**canal**) | HTTPS do ESP32 até a Cloudflare; o ESP32 valida o certificado com `certificados_raiz.h` e recusa a conexão se for inválido. |
| Quem está falando? (**autenticação**) | ESP32: chave `X-Device-Key`. Cuidador: usuário e senha (hash scrypt com salt) e depois cookie de sessão assinado. |
| Pode fazer isso? (**autorização**) | A API confere os vínculos `esp32-borda-01 → patient-0042 → cuidador01`. Dispositivo errado: 403. Outro paciente: 403. ESP32 não cria comando; cuidador não forja ack. |

## Limitações assumidas

- Do túnel até a API o tráfego é HTTP dentro do próprio PC.
- A URL do túnel gratuito muda a cada reinício do `cloudflared`.
- Sinais simulados; sem valor clínico.
- Sem banco, sem múltiplos pacientes, sem limite de tentativas de login.
