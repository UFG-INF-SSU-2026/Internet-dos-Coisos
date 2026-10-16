# Marco 3 — Segurança, autenticação e um novo ciclo produtor-consumidor

**Disciplina:** Software para Sistemas Ubíquos · Instituto de Informática / UFG · 2026/2  
**Grupo:** Internet dos Coisos  
**Cenário:** monitoramento demonstrativo de sinais vitais por *smart clothing*.

> **Protótipo de graduação.** O potenciômetro simula a frequência cardíaca. Os dados **não são médicos** e o projeto não serve para diagnóstico.

## 1. Requisitos e como atendemos

| Requisito do Marco 3 | Como atendemos |
|---|---|
| Evoluir a arquitetura produtor-consumidor do Marco 2 | O ESP32 agora **mede e atua**; a análise foi para a API em Python (`api/regra.py`). A comunicação passou de MQTT para HTTP/REST. |
| Segurança no canal | Toda mensagem do ESP32 vai **assinada** (HMAC-SHA256 com a chave do dispositivo + horário). A chave nunca trafega; mensagem alterada, forjada ou repetida é recusada. O Wokwi não completa HTTPS (decisão D17). |
| Identificação e autenticação dos dispositivos | `deviceId` no corpo + assinatura que só quem tem a chave consegue gerar. |
| Autorização das mensagens | A API confere os vínculos `esp32-borda-01 → patient-0042 → cuidador01` (403 se não bater). |
| Novo ciclo produtor-consumidor | **Ciclo 2:** o cuidador (consumidor no Marco 2) produz o comando "reconhecer alerta"; o ESP32 consome, silencia o buzzer e confirma. |

**Simulação no Wokwi:** <https://wokwi.com/projects/478071248037862401>. O projeto salvo tem o `config.h` de exemplo, sem a chave: para rodar, cole nele o `config.h` gerado (seção 4) e **não salve** com a chave real.

Decisões e o motivo de cada uma: [`docs/decisoes.md`](docs/decisoes.md). Roteiro da apresentação: [`docs/roteiro-apresentacao.md`](docs/roteiro-apresentacao.md).

## 2. Arquitetura

```text
 CICLO 1                                              CICLO 2
 ESP32 ──POST /api/leituras (assinado)──► API         Painel ──POST /api/pacientes/{id}/comando (sessão)──► API
   ▲                                       │ regra.py                                                        │
   └────────── resposta: estado ───────────┤                       ESP32 ◄── GET /api/dispositivo/comando (assinado)
                                           ▼                         │ silencia o buzzer
 Painel ◄── GET /api/pacientes/{id}/estado (sessão)                  └──► POST /api/dispositivo/comando/ack (assinado) ──► API ──► Painel
```

O ESP32 alcança a API do PC por um túnel gratuito da Cloudflare: `ESP32 (Wokwi) ──HTTP assinado──► http://xxxx.trycloudflare.com ──► 127.0.0.1:5000`.

**Como a assinatura funciona:** o ESP32 calcula `HMAC-SHA256(chave, horário + método + rota + corpo)` e manda o resultado nos cabeçalhos `X-Timestamp` e `X-Assinatura`. A API, que tem a mesma chave, recalcula e compara. Sem a chave não dá para assinar; mudar um byte do corpo muda a assinatura; mensagem com mais de 120 s é recusada (não dá para repetir uma mensagem capturada).  
Diagrama editável: [`docs/arquitetura.mmd`](docs/arquitetura.mmd).

### Quem faz o quê

| Componente | Responsabilidade | Arquivo |
|---|---|---|
| ESP32 | lê FC e aceleração a cada 1 s; envia lote de 3 leituras a cada 3 s; liga LED/buzzer conforme o estado; busca comando a cada 3 s; modo local se a API sumir por 8 s | `produtor/sketch.ino` |
| Regra | média das últimas 10 leituras, cobertura mínima de 70%, entra em ATENÇÃO acima de 100 bpm em repouso por 2 avaliações, sai abaixo de 92 bpm; 8 s sem lote = DADOS INSUFICIENTES | `api/regra.py` |
| API | rotas, login, chave do dispositivo, vínculos, comando | `api/app.py` |
| Painel | mostra estado e histórico; botão "Reconhecer alerta" | `api/templates/painel.html` |

### Rotas

| Rota | Quem chama | Autenticação | Autorização | Respostas |
|---|---|---|---|---|
| `GET/POST /login`, `POST /logout` | cuidador | usuário + senha | — | HTML / 303 / 401 |
| `POST /api/leituras` | ESP32 | assinatura HMAC | `deviceId`↔`entityId` | 200, 400, 401, 403 |
| `GET /api/pacientes/{id}/estado` | painel | sessão | cuidador↔paciente | 200, 401, 403 |
| `POST /api/pacientes/{id}/comando` | painel | sessão | cuidador↔paciente | 201, 200 (repetido), 401, 403, 409 (sem alerta) |
| `GET /api/dispositivo/comando` | ESP32 | assinatura HMAC | `deviceId`↔`entityId` | 200 (comando ou `{}`), 401, 403 |
| `POST /api/dispositivo/comando/ack` | ESP32 | assinatura HMAC | `deviceId`↔`entityId` | 200, 401, 403, 404, 409 |

Exemplos de mensagens: [`contrato/leituras-v3.json`](contrato/leituras-v3.json) e [`contrato/comando-v1.json`](contrato/comando-v1.json). Documentação automática: `http://127.0.0.1:5000/docs`.

## 3. Arquivos

```text
marco3/
├── produtor/  sketch.ino, diagram.json, libraries.txt, config.exemplo.h
├── api/       app.py, regra.py, gerar_config.py, requirements*.txt, .env.exemplo, templates/
├── contrato/  leituras-v3.json, comando-v1.json
├── docs/      decisoes.md, roteiro-apresentacao.md, arquitetura.mmd
└── testes/    test_regra.py, test_api.py
```

## 4. Como executar (Windows) — passo a passo

**Precisa de:** Python 3.10+ (`python --version`), navegador e uma conta gratuita no [Wokwi](https://wokwi.com).
Se o terminal não reconhecer `python`, use `py`.

### 4.1 Preparação (só uma vez)

No PowerShell, na pasta **`marco3/api`**:

```powershell
python -m pip install -r requirements.txt
python gerar_config.py
winget install --id Cloudflare.cloudflared
```

- `gerar_config.py` cria `api/.env` (servidor) e `produtor/config.h` (ESP32) com **a mesma chave** do dispositivo.
- Ele mostra a senha do cuidador **uma única vez** (usuário `cuidador01`). **Anote.**
- Esses dois arquivos não vão para o GitHub. Para gerar de novo, apague os dois e rode o script outra vez.
- Depois do `winget`, **feche e reabra** o terminal.

Montar o projeto no Wokwi (uma vez):

1. Em wokwi.com, **New Project → ESP32** (Arduino).
2. Substitua o conteúdo de `sketch.ino` e `diagram.json` pelos de `marco3/produtor/`.
3. Crie (botão **+** / *New file*) os arquivos `libraries.txt` e `config.h`, colando o conteúdo de `marco3/produtor/` (o `config.h` é o **gerado** pelo script).
4. Salve o projeto como **privado** (o `config.h` contém a chave).

### 4.2 A cada demonstração (~2 min)

| # | Onde | O que fazer | Como saber que deu certo |
|---|---|---|---|
| 1 | Terminal 1, pasta `marco3/api` | `python app.py` | `Uvicorn running on http://127.0.0.1:5000` |
| 2 | Terminal 2 (qualquer pasta) | `cloudflared tunnel --url http://127.0.0.1:5000` | aparece um quadro com `https://xxxx.trycloudflare.com` — copie |
| 3 | Wokwi, arquivo `config.h` | troque o valor de `API_BASE_URL` pela URL do passo 2, **trocando `https://` por `http://`** | — |
| 4 | Wokwi | ▶ iniciar a simulação | serial: `WiFi ... conectado` e, a cada 3 s, `lote N: HTTP 200` |
| 5 | Navegador no PC | `http://127.0.0.1:5000/login`, entrar com `cuidador01` + senha anotada | painel mostra `NORMAL` em ~10 s |

Use `127.0.0.1`, não `localhost` (no Windows, `localhost` pode ir para IPv6). A URL do túnel **muda toda vez** que o `cloudflared` reinicia: aí basta atualizar `API_BASE_URL` no Wokwi e reiniciar a simulação.

### 4.3 Se algo der errado

| Sintoma | Causa provável |
|---|---|
| `Execute primeiro: python gerar_config.py` | falta o `api/.env`: rode o passo 4.1 |
| Serial: `HTTP -1` | API ou túnel fechados, URL errada/antiga no `config.h`, URL com `https://` (use `http://`), ou falha simulada ligada (botão vermelho / tecla `f`) |
| Serial: `HTTP 401` | `config.h` do Wokwi com chave diferente do `api/.env` (gere os dois de novo juntos), ou serial mostrou `NTP ... sem horario` (a assinatura leva o horário) |
| Serial: `HTTP 403` | `DEVICE_ID`/`ENTITY_ID` do sketch diferentes do `.env` |
| Serial: `ATENCAO: cole em config.h a URL` | `API_BASE_URL` ainda é o texto de exemplo |
| Painel fica em `SEM DADOS` | nenhum lote chegou: olhe o serial do Wokwi |
| Esqueci a senha | apague `api/.env` e `produtor/config.h`, rode `gerar_config.py` e cole o novo `config.h` no Wokwi |

## 5. O que observar na demonstração

| Ação | Resultado esperado |
|---|---|
| Abrir `/painel` sem login | Redireciona para `/login` |
| Senha errada / certa | Erro / painel liberado |
| Consultar `/api/pacientes/patient-9999/estado` | `403` |
| Potenciômetro acima de 100 bpm, MPU parado | Em ~10 s: painel `ATENCAO`, LED aceso, buzzer |
| Clicar "Reconhecer alerta" | `PENDENTE → ENTREGUE → EXECUTADO`; buzzer silencia, LED continua aceso |
| Potenciômetro abaixo de 92 bpm | Em ~10 s volta a `NORMAL`, LED apaga |
| Potenciômetro no mínimo (abaixo de 30 bpm = leitura inválida) | Em poucos segundos `DADOS_INSUFICIENTES`, LED piscando |
| Botão vermelho / tecla `f` (rede caiu) | Em ~10 s, painel: `DADOS_INSUFICIENTES` e "sem contato recente". ESP32: `MODO LOCAL` após 8 s; a regra mínima continua acionando LED/buzzer. Clicar de novo volta ao normal |
| Chave errada no `config.h` | Serial: `HTTP 401` |

**Testes automáticos** (sem Wokwi), na raiz do repositório:

```powershell
python -m pip install -r marco3/api/requirements-test.txt
python -m unittest discover -s marco3/testes -v
```

`test_regra.py` testa a regra sozinha (persistência, histerese, cobertura, silêncio). `test_api.py` testa login, chave, vínculos e os dois ciclos. A integração Wokwi → túnel → API deve ser ensaiada antes da apresentação.

## 6. Limitações assumidas

- **Sem HTTPS:** o ESP32 simulado no Wokwi não completa nenhum handshake TLS (testado com o túnel e com o Google, com e sem validar certificado; HTTP simples funciona). Por isso as mensagens vão assinadas (HMAC): ninguém forja, altera ou repete uma mensagem, mas as leituras **podem ser lidas** no caminho (não há confidencialidade). Em uma ESP32 real, o próximo passo seria voltar ao HTTPS mantendo a assinatura.
- O túnel gratuito não tem garantia de disponibilidade e troca de URL a cada reinício.
- Sem fila offline: lotes enviados durante a queda são perdidos (decisão D12).
- Dados em memória: reiniciar a API apaga o histórico.
- Um paciente, um cuidador, um ESP32; sem limite de tentativas de login.

---

**Entregas anteriores:** [`../atividade-01.md`](../atividade-01.md), [`../atividade-02.md`](../atividade-02.md) e [`../marco2/README.md`](../marco2/README.md).
