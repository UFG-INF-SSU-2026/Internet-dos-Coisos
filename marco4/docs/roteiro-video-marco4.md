# Roteiro do vídeo — Marco 4 (até 15 minutos)

**O que o vídeo precisa mostrar (enunciado):** os 4 integrantes; o app como segundo produtor; e as quatro verificações: fluxo e contexto, persistência, segurança, falha e recuperação.
O roteiro soma **14 min**, com 1 min de folga. Divisão votada pelo grupo:

| Pessoa | Integrante | Parte |
|---|---|---|
| 1 | Felipe O Carvalho | Introdução, arquitetura e documentação |
| 2 | Murilo Bernardo | Demonstração do sistema no Wokwi e no painel web |
| 3 | Matheus Augusto | Demonstração do aplicativo Android e do contexto |
| 4 | Felipe Alves | Persistência e testes |
Os valores são sintéticos e o paciente é fictício (`patient-0042`).

## Antes de gravar (checklist, ~10 min)

Na raiz do repositório, na `main` atualizada:

| # | Preparação | Como conferir |
|---|---|---|
| 1 | Banco: `DATABASE_URL` no `marco4/api/.env` → `.\.venv\Scripts\python.exe marco4\scripts\verificar_banco.py` | `[OK]` e as 3 hypertables |
| 2 | Terminal 1 (API): `.\.venv\Scripts\python.exe marco4\api\app.py` | `http://127.0.0.1:5000/api/saude` com `"banco_configurado": true` |
| 3 | Terminal 2 (túnel): `cloudflared tunnel --url http://127.0.0.1:5000` | Anotar a URL `https://….trycloudflare.com` |
| 4 | Wokwi no VS Code: `pio run` em `marco4/produtor` → **F1 → Wokwi: Start Simulator** | Serial com `lote N: HTTP 200` |
| 5 | App: instalar `marco4/apk/coisos-cuidador.apk` no emulador ou no celular, **sem fazer login ainda** | Tela "Coisos Cuidador" |
| 6 | Deixar abertos: o diagrama [`visuais/arquitetura-final.svg`](visuais/arquitetura-final.svg), um terminal SQL (`psql` ou o SQL Editor do Tiger Cloud), o [run do CI](https://github.com/UFG-INF-SSU-2026/Internet-dos-Coisos/actions/workflows/testes.yml) e o [`artigo.pdf`](artigo.pdf) | — |
| 7 | Gravação: tela inteira com áudio; janelas do app (emulador com a opção de sensores aberta, em *Extended controls → Virtual sensors*), Wokwi e terminal lado a lado | Testar 10 s de gravação antes |

Se for o emulador: o "balançar o celular" é feito em *Virtual sensors → Accelerometer*, mexendo os eixos; a rede do celular é desligada pela barra de notificações (Wi-Fi e dados).

## Roteiro

| Tempo | Quem | Na tela | O que dizer |
|---|---|---|---|
| 0:00–1:30 | **1. Felipe O Carvalho** | Diagrama da arquitetura | O problema: FC alta durante esforço gera falso alerta. Dois produtores: o ESP32 (FC e movimento) e o **celular do cuidador** (acelerômetro). Fila FIFO única, regra com estado e tempo, TimescaleDB e comando de volta ao ESP32 com ACK |
| 1:30–2:30 | **1. Felipe O Carvalho** | README e artigo | Os 5 itens entregues (APK, persistência, testes, implantação, artigo de 15 páginas); onde ficam as decisões (`decisoes.md`), a verificação com o registro do ensaio (`verificacao.md`) e o guia de implantação |
| 2:30–3:45 | **2. Murilo Bernardo** | Wokwi + serial | Sensor de pulso simulado (chip próprio): o ESP32 detecta os batimentos na onda e calcula a FC; lotes de 3 leituras assinados com **HMAC + horário** (mensagem alterada ou antiga = 401). Tecla **`1`**: coração normal, `lote N: HTTP 200` |
| 3:45–4:30 | **2. Murilo Bernardo** | Painel web (`/login`) | Login do cuidador no painel; estado, gráfico da FC e fila atualizando por WebSocket, sem recarregar a página |
| 4:30–6:00 | **2. Murilo Bernardo** | Wokwi + painel | **Verificação 4, falha e recuperação (ESP32).** Tecla **`3`**: sensor fora do dedo → `DADOS_INSUFICIENTES`. Tecla **`f`**: o ESP32 perde a rede e entra em **modo local** (o buzzer decide sozinho); o painel mostra o dispositivo sem contato. Com a rede de volta, o estado é recalculado. Terminar com a tecla **`1`** |
| 6:00–6:30 | **3. Matheus Augusto** | App: login | URL do túnel (HTTPS), `cuidador01` e a senha; a tela principal mostra **"Tudo bem"**, a FC e o dispositivo **Conectado** |
| 6:30–8:00 | **3. Matheus Augusto** | Wokwi + app | **Verificação 1, fluxo e contexto.** Tecla **`2`** (FC alta em repouso): em ~40 s o app passa a **"Atenção"**. Tocar **Reconhecer alerta**: o quadro mostra "Enviado", "Entregue" e "Alarme silenciado no dispositivo"; na serial, o ESP32 executa o comando e o buzzer para; o botão some |
| 8:00–9:00 | **3. Matheus Augusto** | App + sensores | **Contexto pelo celular:** balançar o celular → "Em movimento, medido pelo celular", e o estado volta a **"Tudo bem"** mesmo com a FC alta (razão `movimento_no_celular`). Parar → o alerta volta em ~20 s |
| 9:00–10:15 | **3. Matheus Augusto** | App + terminal | **Verificação 3, segurança.** Senha errada → "Usuário ou senha incorretos"; URL `http://` recusada pelo app; comandos abaixo: token inválido → **401**, outro paciente → **403**, o próprio → **200**, `http://` → 301 para HTTPS. **Falha no celular:** desligar a rede → faixa "Sem conexão. Mostrando o último estado recebido."; religar → volta em ~3 s |
| 10:15–11:00 | **4. Felipe Alves** | App → **Ver detalhes** | Cobertura, fila FIFO com lotes do ESP32 e do CELULAR intercalados, ciclo do comando e mudanças de estado |
| 11:00–12:30 | **4. Felipe Alves** | Detalhes + SQL + Terminal da API | **Verificação 2, persistência.** "Consultar histórico": `Origem: TimescaleDB`. No SQL: `SELECT count(*) FROM leituras;` e `SELECT ts, estado, razao FROM eventos_estado ORDER BY ts DESC LIMIT 5;`. **Parar a API (Ctrl+C) e subir de novo:** o app mantém o último estado e volta sozinho sem novo login; em Ver detalhes, as transições e o último comando foram **restaurados do banco** (D35); a contagem de leituras só cresceu |
| 12:30–13:15 | **4. Felipe Alves** | GitHub Actions | **Testes:** 54 da API (2 contra o TimescaleDB real no CI), 27 de unidade do app e 2 de interface no emulador do CI, tudo verde no último run da `main` |
| 13:15–14:00 | Todos (~10 s cada) | Artigo | Um resultado por pessoa: processamento rápido diante dos intervalos; o contexto elimina o alerta no movimento e o mantém em repouso; defeitos achados nas medições e no ensaio (relógio do ESP32, D36); limitações: ESP32 sem TLS, fila volátil, sem teste em celular físico |

### Comandos da verificação 3 (PowerShell)

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
