# Roteiro do vídeo — Marco 4 (até 15 minutos)

**O que o vídeo precisa mostrar (enunciado):** os 4 integrantes; o app como segundo produtor; e as quatro verificações: fluxo e contexto, persistência, segurança, falha e recuperação.
O roteiro segue o combinado do grupo: **4 blocos de 3 min, 12 min no total** (3 min de folga para o limite de 15).

| Pessoa | Integrante | Parte |
|---|---|---|
| 1 | Felipe O Carvalho | Introdução e arquitetura (00:00–03:00) |
| 2 | Murilo Bernardo | Demonstração do sistema (03:00–06:00) |
| 3 | Matheus Augusto | Aplicativo e contexto (06:00–09:00) |
| 4 | Felipe Alves | Persistência e testes (09:00–12:00) |
Os valores são sintéticos e o paciente é fictício (`patient-0042`).

## Antes de gravar (checklist, ~10 min)

Na raiz do repositório, na `main` atualizada:

| # | Preparação | Como conferir |
|---|---|---|
| 1 | Banco: `DATABASE_URL` no `marco4/api/.env` → `.\.venv\Scripts\python.exe marco4\scripts\verificar_banco.py` | `[OK]` e as 3 hypertables |
| 2 | Terminal 1 (API): `.\.venv\Scripts\python.exe marco4\api\app.py` | `http://127.0.0.1:5000/api/saude` com `"banco_configurado": true` |
| 3 | Terminal 2 (túnel): `cloudflared tunnel --url http://127.0.0.1:5000` | Anotar a URL `https://….trycloudflare.com` |
| 4 | Wokwi no VS Code: `pio run` em `marco4/produtor` → **F1 → Wokwi: Start Simulator** | Serial com `lote N: HTTP 200` |
| 5 | App: instalar `marco4/apk/coisos-cuidador.apk` no emulador ou no celular e **fazer login antes de gravar** (URL do túnel, `cuidador01`, senha) | Tela principal com "Tudo bem" e "Conectado" |
| 6 | Deixar abertos: o README (diagrama da arquitetura), o painel web logado em `http://127.0.0.1:5000/login`, um terminal SQL (`psql` ou o SQL Editor do Tiger Cloud), o [run do CI](https://github.com/UFG-INF-SSU-2026/Internet-dos-Coisos/actions/workflows/testes.yml) e o [`artigo.pdf`](artigo.pdf) | — |
| 7 | Gravação: tela inteira com áudio; janelas do app (emulador com a opção de sensores aberta, em *Extended controls → Virtual sensors*), Wokwi e terminal lado a lado | Testar 10 s de gravação antes |
| 8 | Aquecer os testes: rodar uma vez `python -m pytest -q` em `marco4/testes` e `.\gradlew.bat testDebugUnitTest` em `marco4/mobile` | A segunda execução do Gradle leva segundos, não minutos |

Se for o emulador: o "balançar o celular" é feito em *Virtual sensors → Accelerometer*, mexendo os eixos; a rede do celular é desligada pela barra de notificações (Wi-Fi e dados).

## Roteiro

Cada bloco cobre os tópicos combinados; a coluna "Verificação" mostra onde aparecem as quatro verificações do enunciado.

### Pessoa 1 — Felipe O Carvalho: introdução e arquitetura (00:00–03:00)

| Tempo | Na tela | O que dizer | Verificação |
|---|---|---|---|
| 0:00–0:40 | README (topo) | **Problema e objetivo:** FC alta durante o esforço gera falso alerta; o objetivo é decidir o alerta pelo contexto de atividade do paciente, com um segundo produtor, o acelerômetro do celular | — |
| 0:40–1:40 | Diagrama do README (seção de arquitetura) | ESP32 no Wokwi e app Android como produtores; API FastAPI com fila FIFO única e um consumidor; regra com estado, tempo e validade do contexto; TimescaleDB; painel web e app; comando de volta ao ESP32 com ACK | — |
| 1:40–2:20 | README, tabela de segurança | **Autenticação e autorização:** ESP32 com HMAC-SHA256 sobre horário, método, rota e corpo (mensagem alterada ou antiga = 401); painel com sessão e senha em hash scrypt; app com token Bearer de 8 h e só HTTPS; vínculo `esp32-borda-01 → patient-0042 → cuidador01` (fora dele = 403). Nenhum segredo no repositório nem no APK. *Opcional:* rodar os comandos abaixo (401, 403, 200) | 3. Segurança |
| 2:20–2:40 | `docs/` | Documentação técnica: decisões (D1–D36), verificação com o registro do ensaio, guia de implantação | — |
| 2:40–3:00 | `artigo.pdf` | Artigo de 15 páginas: pergunta, arquitetura, avaliação (latência, tempos da regra, descarte) e o defeito encontrado nas medições | — |

### Pessoa 2 — Murilo Bernardo: demonstração do sistema (03:00–06:00)

| Tempo | Na tela | O que dizer | Verificação |
|---|---|---|---|
| 3:00–3:40 | Wokwi (circuito) | ESP32, sensor de pulso (chip próprio), MPU6050, potenciômetro, LED e buzzer | — |
| 3:40–4:20 | Wokwi + serial | **Sensores:** o ESP32 detecta os batimentos na onda de pulso e calcula a FC (`bat=` na serial); o MPU6050 mede o movimento. Tecla **`1`**: coração normal | 1. Fluxo |
| 4:20–4:50 | Serial + Terminal da API | **Comunicação com a API:** lotes de 3 leituras assinados; `lote N: HTTP 200` na serial e as requisições chegando no terminal da API | 1. Fluxo |
| 4:50–5:20 | Painel web (`/login`) | **Tempo real:** estado, gráfico da FC e fila atualizando por WebSocket, sem recarregar a página | 1. Fluxo |
| 5:20–6:00 | Wokwi + painel | **Alerta:** tecla **`2`** (FC alta em repouso); em ~40 s o painel passa a `ATENCAO` e o buzzer toca. **Deixar o alerta ativo para a Pessoa 3** | 1. Fluxo |

### Pessoa 3 — Matheus Augusto: aplicativo e contexto (06:00–09:00)

O app já deve estar logado antes deste bloco (login fora do vídeo, para não mostrar a senha).

| Tempo | Na tela | O que dizer | Verificação |
|---|---|---|---|
| 6:00–6:30 | App | **O aplicativo:** a tela principal mostra **"Atenção"**, a FC, o movimento medido pelo ESP32 e o dispositivo **Conectado**; o botão de reconhecer só aparece com alerta | 1. Fluxo |
| 6:30–7:30 | App + sensores do emulador (ou o celular na mão) | **Acelerômetro e contexto:** balançar → "Em movimento, medido pelo celular", e o estado vira **"Tudo bem"** com a FC ainda alta (razão `movimento_no_celular`): o segundo produtor mudou a decisão. Parar → o alerta volta em ~20 s | 1. Contexto |
| 7:30–8:15 | App + serial do Wokwi | **Reconhecer alerta:** o quadro mostra "Enviado", "Entregue" e "Alarme silenciado no dispositivo"; na serial, o ESP32 executa o comando, o buzzer para e o ACK volta; o botão some | 1. Fluxo |
| 8:15–9:00 | App | **Falha e recuperação:** desligar a rede do celular → faixa "Sem conexão. Mostrando o último estado recebido."; religar → volta em ~3 s, sem novo login. *Se sobrar tempo:* tecla **`f`** no Wokwi → o ESP32 entra em modo local e o app mostra "Sem contato" | 4. Falha e recuperação |

### Pessoa 4 — Felipe Alves: persistência e testes (09:00–12:00)

| Tempo | Na tela | O que dizer | Verificação |
|---|---|---|---|
| 9:00–9:30 | `api/sql/timescaledb.sql` | **Por que TimescaleDB:** séries temporais em 3 hypertables (`leituras`, `eventos_estado`, `comandos`); gravação em segundo plano, sem travar o alerta | 2. Persistência |
| 9:30–10:15 | SQL + app → **Ver detalhes** | **Armazenar e consultar:** `SELECT count(*) FROM leituras;` e `SELECT ts, estado, razao FROM eventos_estado ORDER BY ts DESC LIMIT 5;` (aparecem o alerta e o reconhecimento dos blocos anteriores); no app, "Consultar histórico" → `Origem: TimescaleDB` | 2. Persistência |
| 10:15–11:00 | Terminal da API + app | **Reinício:** Ctrl+C na API e subir de novo; o app avisa e volta sozinho; em Ver detalhes, as transições e o último comando foram **restaurados do banco** (D35); a contagem de leituras só cresceu | 2. Persistência, 4. Recuperação |
| 11:00–11:20 | — | **Testes:** 54 da API (regra, rotas, segurança, app, banco simulado e 2 com o TimescaleDB real), 27 de unidade do app e 2 de interface no emulador do CI | — |
| 11:20–12:00 | Terminal + GitHub Actions | **Executar:** `python -m pytest -q` em `marco4/testes` (~10 s) e `.\gradlew.bat testDebugUnitTest` em `marco4/mobile`; mostrar o último run verde da `main` com os 3 jobs | — |

### Comandos opcionais da segurança (Pessoa 1, PowerShell)

A senha é digitada numa janela mascarada, para não aparecer no vídeo.

```powershell
$U = "https://<nome>.trycloudflare.com"
curl.exe -s -o NUL -w "%{http_code}`n" -H "Authorization: Bearer invalido" "$U/api/pacientes/patient-0042/estado"   # 401
$c = Get-Credential cuidador01
$corpo = @{ usuario = "cuidador01"; senha = $c.GetNetworkCredential().Password } | ConvertTo-Json
$t = (Invoke-RestMethod -Method Post -Uri "$U/api/app/login" -ContentType "application/json" -Body $corpo).token
curl.exe -s -o NUL -w "%{http_code}`n" -H "Authorization: Bearer $t" "$U/api/pacientes/patient-9999/estado"   # 403
curl.exe -s -o NUL -w "%{http_code}`n" -H "Authorization: Bearer $t" "$U/api/pacientes/patient-0042/estado"   # 200
curl.exe -s -o NUL -w "%{http_code}`n" "http://$($U.Substring(8))/api/saude"                                    # 301 para HTTPS
```

## Se algo der errado durante a gravação

| Sintoma | O que fazer |
|---|---|
| App em "Sem contato" com a serial mostrando `HTTP 401` | Relógio do ESP32 atrasado: esperar a próxima resposta da API (D36 corrige sozinho) ou reiniciar o simulador |
| "Atenção" demora mais de 1 min | O Wokwi anda a ~35% do tempo real; esperar, ou cortar na edição |
| Túnel reiniciou | A URL muda: refazer o login com a URL nova |
| Login do app falha com "Sem conexão com a API" | Conferir a URL do túnel (`https://`, sem barra no fim) e o Terminal 1 |

## Depois de gravar

1. Publicar o vídeo (YouTube não listado ou Drive com acesso por link).
2. Preencher no [`README.md`](../README.md) a seção **Vídeo do Marco 4**: link e o commit demonstrado (`git rev-parse --short HEAD`).
3. Marcar no `PLANO_MARCO4.md` os itens do vídeo.
