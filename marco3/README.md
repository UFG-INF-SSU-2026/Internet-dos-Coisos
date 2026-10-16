# Marco 3 — Segurança, autenticação e um novo ciclo produtor-consumidor

**Disciplina:** Software para Sistemas Ubíquos · Instituto de Informática / UFG · 2026/2  
**Grupo:** Internet dos Coisos  
**Cenário:** monitoramento demonstrativo de sinais vitais por *smart clothing*.

> **Protótipo de graduação.** O potenciômetro simula a frequência cardíaca. Os dados **não são médicos** e o projeto não serve para diagnóstico.

## 1. Requisitos e como atendemos

| Requisito do Marco 3 | Como atendemos |
|---|---|
| Evoluir a arquitetura produtor-consumidor do Marco 2 | O ESP32 agora **mede e atua**; a análise foi para a API em Python (`api/regra.py`). A comunicação passou de MQTT para HTTPS/REST. |
| Segurança no canal | HTTPS do ESP32 até o túnel Cloudflare, com **certificado validado** no ESP32 (`certificados_raiz.h`). |
| Identificação e autenticação dos dispositivos | `deviceId` + chave `X-Device-Key` em toda requisição do ESP32. |
| Autorização das mensagens | A API confere os vínculos `esp32-borda-01 → patient-0042 → cuidador01` (403 se não bater). |
| Novo ciclo produtor-consumidor | **Ciclo 2:** o cuidador (consumidor no Marco 2) produz o comando "reconhecer alerta"; o ESP32 consome, silencia o buzzer e confirma. |

Decisões e o motivo de cada uma: [`docs/decisoes.md`](docs/decisoes.md). Roteiro da apresentação: [`docs/roteiro-apresentacao.md`](docs/roteiro-apresentacao.md).

## 2. Arquitetura

```text
 CICLO 1                                              CICLO 2
 ESP32 ──HTTPS POST /api/leituras (chave)──► API      Painel ──POST /api/pacientes/{id}/comando (sessão)──► API
   ▲                                          │ regra.py                                                     │
   └────────── resposta: estado ──────────────┤                    ESP32 ◄── HTTPS GET /api/dispositivo/comando (chave)
                                              ▼                      │ silencia o buzzer
 Painel ◄── GET /api/pacientes/{id}/estado (sessão)                  └──► HTTPS POST /api/dispositivo/comando/ack (chave) ──► API ──► Painel
```

O ESP32 alcança a API do PC por um túnel gratuito da Cloudflare: `ESP32 (Wokwi) ──HTTPS──► https://xxxx.trycloudflare.com ──► 127.0.0.1:5000`.  
Diagrama editável: [`docs/arquitetura.mmd`](docs/arquitetura.mmd).

### Quem faz o quê

| Componente | Responsabilidade | Arquivo |
|---|---|---|
| ESP32 | lê FC e aceleração a cada 1 s; envia lote de 5 leituras; liga LED/buzzer conforme o estado; busca comando a cada 5 s; modo local se a API sumir por 15 s | `produtor/sketch.ino` |
| Regra | janela de 20 s, cobertura mínima de 70%, entra em ATENÇÃO acima de 100 bpm em repouso por 2 avaliações, sai abaixo de 92 bpm | `api/regra.py` |
| API | rotas, login, chave do dispositivo, vínculos, comando | `api/app.py` |
| Painel | mostra estado e histórico; botão "Reconhecer alerta" | `api/templates/painel.html` |

### Rotas

| Rota | Quem chama | Autenticação | Autorização | Respostas |
|---|---|---|---|---|
| `GET/POST /login`, `POST /logout` | cuidador | usuário + senha | — | HTML / 303 / 401 |
| `POST /api/leituras` | ESP32 | `X-Device-Key` | `deviceId`↔`entityId` | 200, 400, 401, 403 |
| `GET /api/pacientes/{id}/estado` | painel | sessão | cuidador↔paciente | 200, 401, 403 |
| `POST /api/pacientes/{id}/comando` | painel | sessão | cuidador↔paciente | 201, 200 (repetido), 401, 403, 409 (sem alerta) |
| `GET /api/dispositivo/comando` | ESP32 | `X-Device-Key` | `deviceId`↔`entityId` | 200 (comando ou `{}`), 401, 403 |
| `POST /api/dispositivo/comando/ack` | ESP32 | `X-Device-Key` | `deviceId`↔`entityId` | 200, 401, 403, 404, 409 |

Exemplos de mensagens: [`contrato/leituras-v3.json`](contrato/leituras-v3.json) e [`contrato/comando-v1.json`](contrato/comando-v1.json). Documentação automática: `http://127.0.0.1:5000/docs`.

## 3. Arquivos

```text
marco3/
├── produtor/  sketch.ino, diagram.json, libraries.txt, certificados_raiz.h, config.exemplo.h
├── api/       app.py, regra.py, gerar_config.py, requirements*.txt, .env.exemplo, templates/
├── contrato/  leituras-v3.json, comando-v1.json
├── docs/      decisoes.md, roteiro-apresentacao.md, arquitetura.mmd
└── testes/    test_regra.py, test_api.py
```

## 4. Como executar (Windows)

**Uma vez**, em `marco3/api`:

```powershell
python -m pip install -r requirements.txt
python gerar_config.py
winget install --id Cloudflare.cloudflared
```

`gerar_config.py` cria `api/.env` e `produtor/config.h` com **a mesma chave** do dispositivo e mostra a senha do cuidador (usuário `cuidador01`) **uma única vez**. Esses dois arquivos não vão para o GitHub. Para gerar de novo, apague os dois e rode o script outra vez.

**A cada demonstração:**

1. Terminal 1 (`marco3/api`): `python app.py`
2. Terminal 2: `cloudflared tunnel --url http://127.0.0.1:5000` e copie a URL `https://xxxx.trycloudflare.com`. Use `127.0.0.1`, não `localhost`.
3. Wokwi: projeto ESP32 com `sketch.ino`, `diagram.json`, `libraries.txt`, `certificados_raiz.h` e o `config.h` gerado. Em `config.h`, cole a URL do passo 2 em `API_BASE_URL`. Não deixe esse projeto público (tem a chave).
4. Inicie a simulação. O serial deve mostrar `lote N: HTTP 200`.
5. No PC: `http://127.0.0.1:5000/login`.

A URL do túnel muda sempre que o `cloudflared` reinicia: atualize só `API_BASE_URL`.  
Serial com `HTTP -1`: confira API, túnel, URL no `config.h` e se a falha simulada (botão vermelho / tecla `f`) está desligada.

## 5. O que observar na demonstração

| Ação | Resultado esperado |
|---|---|
| Abrir `/painel` sem login | Redireciona para `/login` |
| Senha errada / certa | Erro / painel liberado |
| Consultar `/api/pacientes/patient-9999/estado` | `403` |
| Potenciômetro acima de 100 bpm, MPU parado | Em 15–25 s: painel `ATENCAO`, LED aceso, buzzer |
| Clicar "Reconhecer alerta" | `PENDENTE → ENTREGUE → EXECUTADO`; buzzer silencia, LED continua aceso |
| Potenciômetro abaixo de 92 bpm | Volta a `NORMAL`, LED apaga |
| Botão verde (sensor desconectado) | `DADOS_INSUFICIENTES`, LED piscando |
| Botão vermelho / tecla `f` (rede caiu) | Painel: `DADOS_INSUFICIENTES` e "sem contato recente". ESP32: `MODO LOCAL` após 15 s, regra mínima continua acionando LED/buzzer |
| Chave errada no `config.h` | Serial: `HTTP 401` |

**Testes automáticos** (sem Wokwi), na raiz do repositório:

```powershell
python -m pip install -r marco3/api/requirements-test.txt
python -m unittest discover -s marco3/testes -v
```

`test_regra.py` testa a regra sozinha (persistência, histerese, cobertura, silêncio). `test_api.py` testa login, chave, vínculos e os dois ciclos. A integração Wokwi → túnel → API deve ser ensaiada antes da apresentação.

## 6. Limitações assumidas

- Do túnel até a API o tráfego é HTTP, dentro do próprio PC.
- O túnel gratuito não tem garantia de disponibilidade e troca de URL a cada reinício.
- Sem fila offline: lotes enviados durante a queda são perdidos (decisão D12).
- Dados em memória: reiniciar a API apaga o histórico.
- Um paciente, um cuidador, um ESP32; sem limite de tentativas de login.
- O botão verde do circuito tem o rótulo "silenciar" (herdado do Marco 2): ele simula o **sensor desconectado**, não silencia o alarme.

---

**Entregas anteriores:** [`../atividade-01.md`](../atividade-01.md), [`../atividade-02.md`](../atividade-02.md) e [`../marco2/README.md`](../marco2/README.md).
