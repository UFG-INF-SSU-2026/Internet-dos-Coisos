# Verificação do Marco 4

Este documento reúne as quatro verificações pedidas no enunciado: fluxo e contexto, persistência, segurança, e falha e recuperação.
Para cada uma, registra o que os testes automatizados comprovam e o roteiro do ensaio manual com o sistema completo.
Como preparar o ambiente está no [guia de implantação](implantacao.md).

## 1. Testes automatizados

Em `marco4/testes`, com as dependências instaladas:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -v --junitxml=relatorio-junit.xml test_regra.py test_api.py test_melhorias.py test_consolidacao.py test_app_mobile.py
```

A suíte não precisa de Wokwi, banco ou rede. A API roda dentro do processo com `TestClient`, as credenciais são geradas por teste, o relógio monotônico é controlado e o TimescaleDB é trocado por um objeto simulado (`FakeHistorico`).

**Resultado registrado:** 50 testes aprovados.
- Execução local: [`evidencias/testes-api.txt`](evidencias/testes-api.txt), com Python 3.14 no commit `178cf38`. Os testes mais novos cobrem o silêncio adaptativo e o `online` que acompanha o ritmo dos lotes (D32).
- CI no GitHub Actions: roda a cada push na `main`, com Python 3.10 e 3.12 ([histórico de execuções](https://github.com/UFG-INF-SSU-2026/Internet-dos-Coisos/actions/workflows/testes.yml)). A primeira execução, com 42 testes, foi o [run 46039476817](https://github.com/UFG-INF-SSU-2026/Internet-dos-Coisos/actions/runs/46039476817) no merge `6f1a443`. Os relatórios JUnit ficam nos artefatos `relatorio-junit-py3.10` e `relatorio-junit-py3.12`.

### Módulos e requisitos cobertos

| Arquivo de teste | Módulo exercitado | Requisito coberto | Testes |
|---|---|---|---|
| `test_regra.py` | `api/regra.py` | Regra com estado e tempo: janela, cobertura, persistência, histerese, silêncio (fixo e adaptativo) | 12 |
| `test_api.py` | `api/app.py` (rotas do ESP32 e do painel) | Autenticação HMAC, autorização dispositivo/paciente/cuidador, ciclo 1 e ciclo 2, `online` adaptativo | 13 |
| `test_melhorias.py` | `app.py` (fila, WebSocket, histórico) | Fila FIFO, WebSocket autenticado, `/api/saude` sem dados pessoais | 6 |
| `test_consolidacao.py` | `app.py` + `temporal.py` + `gerar_config.py` | Gravação de leituras, transições e comandos; consulta do histórico; segredos fora do Git | 4 |
| `test_app_mobile.py` | `app.py` (rotas do app) + `regra.py` (contexto) | Token do app, segundo produtor, validade e atraso, mudança de contexto, ciclo 2 pelo app | 15 |

### Testes de unidade do app Android

Em `marco4/mobile`, rodam na JVM, sem emulador:

```powershell
.\gradlew.bat testDebugUnitTest
```

A lógica que não depende do Android fica em [`Logica.kt`](../mobile/app/src/main/java/br/ufg/coisos/Logica.kt). O `Movimento`, a `Api` e a tela usam essas funções, então o teste exercita o mesmo código do APK.

| Classe de teste | Função exercitada | O que comprova | Testes |
|---|---|---|---|
| `IntensidadeTest` | `intensidadeMovimento` | Celular parado dá 0 em qualquer posição; a sacudida do ensaio (0,83 g) passa de 0,15 g; tremor pequeno fica abaixo | 5 |
| `UrlTest` | `urlDaApi` | Só aceita `https://`; recusa `http://`, vazio e URL sem esquema | 4 |
| `CorpoMovimentoTest` | `corpoMovimento` | Corpo igual ao contrato `app-v1`; intensidade limitada a 0–8 | 2 |
| `ResumoTest` | `Resumo.de` | Leitura do `/estado`; campos nulos viram "—" (regressão do ensaio 2.0); botão só ativo em `ATENCAO` | 4 |
| `ApresentacaoTest` | `aparenciaDoEstado`, `textoMovimento`, `textoComando`, `horaLocal` | Textos da tela em português; FC arredondada; hora da API no fuso do celular | 4 |
| `ComandoDoAlertaTest` | `Resumo.de` (`comandoDesteAlerta`) | O reconhecimento só aparece, e o botão só some, para o alerta atual (regressão do ensaio completo) | 4 |

**Resultado registrado:** 23 testes aprovados.
- Execução local: [`evidencias/testes-app.txt`](evidencias/testes-app.txt).
- CI: job `app-android` do mesmo workflow. Roda os testes, gera o APK e guarda os artefatos `relatorio-junit-app` e `coisos-cuidador-debug-apk`.

### Entradas, resultado esperado e resultado observado

| Requisito | Entrada e ação | Resultado esperado e observado | Teste |
|---|---|---|---|
| Dois produtores na mesma fila | Lote do ESP32 e depois leitura de movimento do app | Os dois passam pelo mesmo consumidor FIFO, nesta ordem: `ultimosLotesProcessados` = `esp32`, `celular`. **Observado: passou.** | `test_leituras_do_celular_passam_pela_fila` |
| Decisão | Lotes com FC 120 bpm em repouso | `NORMAL` → `ATENCAO` só depois de 2 avaliações e com a janela coberta. **Observado: passou.** | `test_fc_alta_em_repouso_precisa_persistir`, `test_ciclo1_leituras_viram_estado_no_painel` |
| Mudança de contexto | FC 120 bpm, MPU6050 em repouso e celular balançando (0,6 g) | Nunca entra em `ATENCAO`; `fonteMovimento = celular`; reconhecer alerta devolve 409. **Observado: passou.** | `test_movimento_do_celular_suprime_alerta` |
| Contexto encerra alerta | `ATENCAO` ativo e, depois de 5 s, o celular reporta 0,8 g | Volta para `NORMAL` com `razao = movimento_no_celular`. **Observado: passou.** | `test_celular_parado_mantem_alerta_e_balancar_encerra` |
| Validade do contexto | Celular balança uma vez e para de enviar por 10 s | O contexto expira (mais de 6 s) e a FC alta volta a gerar `ATENCAO`. **Observado: passou.** | `test_contexto_do_celular_expira`, `test_contexto_vale_por_poucos_segundos` |
| Celular não acelera o alerta | 1 lote com FC alta e várias leituras do celular parado | `ATENCAO` só depois do 2º lote do ESP32; leituras do celular não contam para a persistência. **Observado: passou.** | `test_leitura_do_celular_nao_acelera_o_alerta` |
| Atraso | Leitura do celular capturada há 15 s, com relógio 30 s adiantado, e uma mais antiga que a última aceita | 422 com `atrasada`, `relogio_adiantado` e `fora_de_ordem`; o contador mostra 1 recebida e 3 descartadas. **Observado: passou.** | `test_leitura_do_celular_atrasada_e_rejeitada` |
| Resposta (ciclo 2) | Cuidador reconhece o alerta, o ESP32 busca o comando e envia ACK | `PENDENTE → ENTREGUE → EXECUTADO`; com token, o comando registra `canal = app`. **Observado: passou.** | `test_ciclo2_comando_e_ack`, `test_app_reconhece_alerta_com_token` |
| Persistência | 3 lotes, transição e comando com o banco simulado | Grava 3 lotes, a transição e `PENDENTE`, `ENTREGUE` e `EXECUTADO`; `/historico` responde com `origem = TimescaleDB`. **Observado: passou.** | `test_grava_leituras_transicoes_e_retorna_historico`, `test_grava_atuacoes_no_segundo_ciclo` |
| Identidade inválida | Token inválido, vazio, com esquema `Basic`, forjado com outro segredo ou expirado | 401 no estado, no comando e nas leituras do app. **Observado: passou.** | `test_token_invalido_401`, `test_token_expirado_401` |
| Identidade inválida (ESP32) | Sem assinatura, chave errada, corpo alterado ou assinatura de 300 s atrás | 401. **Observado: passou.** | `test_assinatura_do_dispositivo`, `test_corpo_alterado_invalida_assinatura`, `test_mensagem_antiga_recusada` |
| Fora da permissão | Cuidador autenticado acessando `patient-9999` (sessão ou token); ESP32 não vinculado | 403. **Observado: passou.** | `test_token_de_outro_paciente_403`, `test_cuidador_nao_ve_outro_paciente`, `test_dispositivo_nao_vinculado` |
| Papéis | ESP32 tentando criar comando; cuidador tentando forjar ACK | 401 nos dois casos. **Observado: passou.** | `test_ciclo2_quem_pode_o_que` |
| Celular durante a falha do ESP32 | Paciente em `DADOS_INSUFICIENTES` por silêncio e chega uma leitura do celular | Continua em `DADOS_INSUFICIENTES`; a janela antiga não é reavaliada. **Observado: passou.** | `test_celular_nao_tira_de_dados_insuficientes_com_esp32_em_silencio` |
| Falha de comunicação | 40 s sem lote do ESP32 (13 s no teste da regra) | `DADOS_INSUFICIENTES` com `razao = sem_leituras_recentes` e `online = false`. **Observado: passou.** O retorno com novos lotes é verificado no ensaio 2.4. | `test_ciclo1_silencio_vira_dados_insuficientes`, `test_silencio_vira_dados_insuficientes` |
| Segredos fora do Git | `gerar_config.py` em pasta temporária, rodado duas vezes | Cria `.env` e `config.h` com a mesma chave e não sobrescreve na segunda execução. **Observado: passou.** | `test_gera_config_e_preserva_em_segunda_execucao`, `test_recria_config_esp32_quando_env_ja_existe` |

### Medições reprodutíveis

O script [`../scripts/avaliar.py`](../scripts/avaliar.py) mede, sem rede nem banco, a latência de processamento na API, o custo do login, os tempos de decisão da regra com relógio simulado e o descarte de leituras atrasadas. A saída registrada está em [`evidencias/avaliacao.txt`](evidencias/avaliacao.txt), e os números são discutidos no artigo.

## 2. Ensaio com o sistema completo

O ensaio completo foi feito em 27/11/2026, com todas as peças ligadas ao mesmo tempo:
- **ESP32:** Wokwi do VS Code, com o sensor de pulso (D34) e o gateway local até a API (D33).
- **API e banco:** API com TimescaleDB (imagem `timescale/timescaledb:latest-pg17` no Docker), com credenciais temporárias.
- **App:** APK no emulador do Android Studio, pela URL HTTPS de um túnel `trycloudflare.com`.
- **Celular físico:** o grupo decidiu não testar. O acelerômetro do emulador (`adb emu sensor set acceleration`) fez o papel do balanço do celular.

Um roteiro conduziu o app por `adb` e mandou as teclas ao ESP32 pela serial RFC2217. Cada passo esperou o texto aparecer na tela e registrou a hora.
Evidências: [`evidencias/ensaio-completo.txt`](evidencias/ensaio-completo.txt) (roteiro, SQL antes e depois do reinício, serial) e [`evidencias/app/completo/`](evidencias/app/completo/) (prints `cNN`).

Versão ensaiada: commit `2c77e3a`, APK `coisos-cuidador.apk` (SHA-256 `ef84dce2a0392dd3e0c5119764b8207f52a7264808dbb36748a53fa3d8a4cd7d`), Android API 37 (emulador), 27/11/2026.
O ensaio levou a quatro correções, descritas em [Defeitos encontrados no ensaio completo](#defeitos-encontrados-no-ensaio-completo); a tabela registra a última execução, já com elas.

### 2.0 Ensaio preliminar no emulador (27/11/2026)

Antes do ensaio com o celular, o APK foi testado no emulador do Android Studio (Medium Phone, Android API 37, 1080×2400).
- **API:** a versão deste commit, com credenciais temporárias e **sem banco**, exposta por um túnel `trycloudflare.com` real (HTTPS).
- **ESP32:** substituído por um script que envia lotes assinados com HMAC a cada 3 s (FC 120 bpm, `g = 1.0`), busca o comando e devolve o ACK. Log em [`evidencias/ensaio-emulador-esp32-sim.txt`](evidencias/ensaio-emulador-esp32-sim.txt).
- **Movimento:** simulado com `adb emu sensor set acceleration`.
- **Prints:** estão em [`evidencias/app/`](evidencias/app/).

Este ensaio veio antes do ensaio completo, registrado nas tabelas 2.1 a 2.4. A interface do app mudou depois; os prints atuais estão em `evidencias/app/completo/`.

| Verificação | Observado | Evidência |
|---|---|---|
| Tela de login | Campos URL, usuário e senha; senha mascarada | `01-login.png` |
| Senha errada pelo túnel HTTPS | "Usuário ou senha incorretos" | `03-senha-errada.png` |
| URL com `http://` | Recusada antes de qualquer requisição: "Use a URL https:// do túnel" | `11-http-recusado.png` |
| Login correto, sem ESP32 | `SEM_DADOS`, "ESP32 sem contato recente", botão desativado | `04-sem-dados.png` |
| FC 120 em repouso | `ATENCAO` 12 s depois do primeiro lote (16:00:17 → 16:00:29 no log); "ESP32 online"; botão ativo | `05-atencao.png` |
| Tocar **Reconhecer alerta** | No lote seguinte, o ESP32 simulado recebeu `cmd-f5137cd9` e respondeu ACK; o app mostrou `EXECUTADO` no cartão e "Reconhecimento enviado" abaixo do botão | `06-reconhecido.png`, linha 16:00:38 do log |
| Balançar o celular (0,83 g) | `NORMAL`, `Movimento: ACTIVE (fonte: celular)`, botão desativado; no log, a passagem de `ATENCAO` para `NORMAL` acontece entre dois lotes (3 s) | `07-contexto-movimento.png` |
| Parar de balançar | `ATENCAO` de volta com `fonte: esp32` | `08-alerta-volta.png` |
| Wi-Fi e dados desligados no emulador | "Erro de rede … Mostrando o último estado recebido"; envio do acelerômetro falha; nenhum travamento | `09-sem-rede.png` |
| Rede religada | Atualização volta sozinha, sem novo login | `10-rede-voltou.png` |
| ESP32 simulado encerrado | `DADOS_INSUFICIENTES` e "ESP32 sem contato recente"; botão desativado | `12-sem-esp32.png` |

**Defeitos encontrados e corrigidos no app:**
- `optString` do `org.json` devolvia o texto `"null"` para campos JSON nulos, e a tela mostrava "Último contato: null" e "enviado (null)". Uma função `texto()` passou a trocar o nulo por "—".
- A linha abaixo do botão mostrava "Comando … PENDENTE" para sempre, enquanto o cartão já dizia `EXECUTADO`. Agora ela mostra "Reconhecimento enviado (…). Acompanhe o status no cartão", e o status real fica só no cartão.

Os prints foram refeitos com o APK corrigido, o mesmo que está em `apk/`. O defeito do "null" ficou coberto pelo teste `campos_nulos_viram_traco_e_nao_o_texto_null`.

### 2.0b Ensaio com o ESP32 no Wokwi do VS Code (27/11/2026)

O ESP32 simulado no Wokwi do VS Code usou o mesmo `sketch.ino` e o mesmo `diagram.json`, compilados com PlatformIO.
- **Caminho de rede:** o ESP32 falou com a API pelo gateway local (`host.wokwi.internal`, D33), e o app falou com a API pelo túnel HTTPS.
- **Controle:** as teclas foram enviadas pela serial RFC2217 (porta 4000).
- **API:** ensaio sem banco, com a regra de silêncio adaptativo (D32).
- **Registros:** log da serial em [`evidencias/ensaio-wokwi-serial.txt`](evidencias/ensaio-wokwi-serial.txt) e prints em [`evidencias/app/wokwi/`](evidencias/app/wokwi/).

**Primeira tentativa, que motivou D32 e D33:**
- Pelo túnel, todo lote recebeu `HTTP 301`, porque a Cloudflare passou a redirecionar `http://` para HTTPS.
- Pelo gateway local, os lotes chegaram, mas a simulação rodava a ~40% da velocidade real: lotes de 3 s chegavam a cada 7–10 s de relógio. Com o silêncio fixo de 8 s, o estado alternava `ATENCAO`/`NORMAL`/`DADOS_INSUFICIENTES`.

**Segunda tentativa, com as correções:**

| Passo (hora) | Observado | Evidência |
|---|---|---|
| API reiniciada com o app aberto | O token antigo deixou de valer: o app voltou ao login com "Sessão expirou, entre de novo" | `w0-sessao-expirou.png` |
| Tecla `1` (16:51:19) | `NORMAL` (`condicao_cessou`) | `x1-normal.png` |
| Tecla `2` (16:51:54) | `ATENCAO` às 16:52:17, estável durante o alerta: nenhuma alternância por silêncio | `x2-atencao.png` |
| **Reconhecer alerta** no app | O ESP32 do Wokwi recebeu `cmd-3433f8fc` às 16:52:49, silenciou o buzzer e respondeu ACK (HTTP 200); o comando ficou `EXECUTADO` com `canal = app` | `x3-reconhecido.png`, log 16:52:49 |
| Acelerômetro do emulador em 0,83 g (16:53:02) | `NORMAL` às 16:53:09 com `razao = movimento_no_celular` e `fonte: celular` | `x4-contexto.png` |
| Movimento parado (16:53:15) | `ATENCAO` de novo às 16:53:28, com `fonte: esp32` | `x5-alerta-volta.png` |
| Tecla `f`, queda de rede do ESP32 (16:53:49) | Lotes com `HTTP -1`; o ESP32 entrou em **MODO LOCAL** às 16:54:15 com o alerta local (FC 135 em repouso); o app mostrou `DADOS_INSUFICIENTES` e "ESP32 sem contato recente" | `x6-esp32-sem-rede.png`, log 16:54:15 |
| Tecla `f` de novo (16:54:34) | Às 16:54:37: "API respondeu: estado volta a vir da API", lote com HTTP 200; `ATENCAO` às 16:54:45 | `x7-recuperado.png` |

Neste ensaio não foram verificados o TimescaleDB e o certificado; os dois entraram no ensaio completo (2.2 e 2.3).

### 2.0c Sensor de pulso no Wokwi (27/11/2026)

Depois da troca do potenciômetro pelo sensor de pulso simulado (D34), cada cenário foi repetido no Wokwi do VS Code, com a FC medida pela detecção de batimentos do ESP32.
O log está em [`evidencias/ensaio-sensor-pulso.txt`](evidencias/ensaio-sensor-pulso.txt).

| Entrada no chip | FC medida pelo ESP32 | Estado na API |
|---|---|---|
| Potenciômetro no meio (125 bpm), cenário `0` | 125,0 bpm, estável | `ATENCAO` (repouso) |
| Cenário `1`: coração a 78 bpm | 76,9–78,9 bpm a partir do 4º batimento | `NORMAL` |
| Cenário `2`: coração a 135 bpm | 136,4 bpm | `ATENCAO` |
| Cenário `3`: sensor fora do dedo | batimentos param; FC inválida (`null`) em ~3 s | `DADOS_INSUFICIENTES` |
| Cenário `4`: 135 bpm com artefato de movimento (g = 1,75) | 97–120 bpm, oscilando: o balanço cria e esconde picos | `NORMAL` (movimento explica a FC) |

Com o chip, a simulação ficou em ~32% da velocidade real; o silêncio adaptativo (D32) absorveu a diferença.
Na primeira montagem, os cenários `1` e `2` não mudavam a FC, porque o Wokwi não simula o DAC do ESP32; o ritmo passou a ser escolhido por dois pinos digitais.
O Wokwi do VS Code só relê o `diagram.json` e a lista de pinos do chip ao reiniciar o simulador.

### 2.1 Fluxo e contexto

| Passo | Resultado esperado | Registro |
|---|---|---|
| Entrar no app com `cuidador01` pela URL `https://…trycloudflare.com` | Tela de estado carrega; o dispositivo aparece como conectado | 19:02:56, tela em 5 s; "Dispositivo: Conectado" 15 s depois ([`c02-normal`](evidencias/app/completo/c02-normal.png)) |
| Wokwi, tecla `1` (FC normal) | App e painel mostram `NORMAL` | "Tudo bem", 79 bpm medidos na onda de pulso ([`c02-normal`](evidencias/app/completo/c02-normal.png)) |
| Wokwi, tecla `2` (FC alta em repouso), com o celular parado na mesa | `ATENCAO` em cerca de 10 s; LED e buzzer ligam; o botão **Reconhecer alerta** fica ativo | `ATENCAO` às 19:04:50 (48 s de relógio, com o Wokwi a ~35% da velocidade real); botão visível ([`c03-atencao`](evidencias/app/completo/c03-atencao.png)) |
| Tocar **Reconhecer alerta** no app | Comando `PENDENTE → ENTREGUE → EXECUTADO`; o buzzer silencia e o LED continua aceso | `cmd-57bee09c`: `PENDENTE` 19:04:59, `ENTREGUE` e `EXECUTADO` 19:05:08 (banco); serial "buzzer silenciado; ack HTTP 200"; o botão some e aparece "Alarme silenciado no dispositivo" ([`c04-reconhecido`](evidencias/app/completo/c04-reconhecido.png)) |
| Ainda na tecla `2`, balançar o celular | Movimento com `fonte: celular`; alerta encerrado com `razao = movimento_no_celular` | Acelerômetro do emulador em 0,83 g: "Em movimento, medido pelo celular" em 8 s e `NORMAL` com `movimento_no_celular` às 19:05:17 ([`c05-movimento-celular`](evidencias/app/completo/c05-movimento-celular.png)) |
| Parar de balançar | Depois de cerca de 6 s o contexto expira e a FC alta volta a gerar `ATENCAO` | `ATENCAO` às 19:05:44, 21 s depois de parar ([`c06-alerta-volta`](evidencias/app/completo/c06-alerta-volta.png)) |
| Wokwi, tecla `4` (135 bpm com movimento no MPU6050 e artefato no sensor de pulso) | `NORMAL`: o movimento medido pelo ESP32 explica a FC | `NORMAL` às 19:06:07 ([`c07-movimento-esp32`](evidencias/app/completo/c07-movimento-esp32.png)) |

### 2.2 Persistência

| Passo | Resultado esperado | Registro |
|---|---|---|
| Rodar o fluxo 2.1 e executar `SELECT count(*) FROM leituras;` | Contagem maior que zero | 768 leituras (767 com FC; a inválida é o sensor sem batimento); 3 hypertables; 10 transições deste ensaio |
| Parar a API (`Ctrl+C`) e iniciá-la de novo | `/api/saude` mostra `banco_ativo` | `"banco_ativo":true` às 19:13 |
| Repetir as consultas de `leituras`, `eventos_estado` e `comandos` | A contagem não volta a zero; aparecem a transição `movimento_no_celular` e o comando `EXECUTADO` | 780 leituras (as 768 e os lotes novos); `NORMAL / movimento_no_celular` e `cmd-57bee09c / EXECUTADO` continuam no banco |
| `GET /api/pacientes/patient-0042/historico` (painel logado) | `origem: TimescaleDB` com as leituras anteriores ao reinício | `origem: TimescaleDB`, 100 leituras de 19:06:16 a 19:13:33, a maioria de antes do reinício. Como a API do ensaio gerou outra `APP_SECRET_KEY`, o app pediu novo login ("Sessão expirou"), mantendo a URL e o usuário ([`c11-sessao-expirou`](evidencias/app/completo/c11-sessao-expirou.png), [`c12-relogin`](evidencias/app/completo/c12-relogin.png)) |

### 2.3 Segurança

| Passo | Resultado esperado | Registro |
|---|---|---|
| Login no app com senha errada | Mensagem "Usuário ou senha incorretos" (401) | Mensagem em 3 s ([`c17-senha-errada`](evidencias/app/completo/c17-senha-errada.png)) |
| `curl.exe -i -H "Authorization: Bearer invalido" https://…/api/pacientes/patient-0042/estado` | 401 | 401, pelo túnel |
| Com um token válido, `GET /api/pacientes/patient-9999/estado` | 403 | 403 (e 200 para `patient-0042` com o mesmo token) |
| No app, digitar a URL com `http://` | O app recusa: "Use a URL https:// do túnel" | Recusada antes de qualquer requisição ([`c18-http-recusado`](evidencias/app/completo/c18-http-recusado.png)); o túnel também responde `301` para `http://` |
| Abrir a URL do túnel no navegador e ver o certificado | Certificado válido para `*.trycloudflare.com`, emitido por uma CA pública | Validado (cadeia e nome) pelo `ssl` do Python: TLS 1.3, `*.trycloudflare.com`, emissor Google Trust Services WE1, válido até 03/01/2027 |

**Canal:**
- O app fala HTTPS com a borda da Cloudflare, e o Android valida o certificado e o nome do serviço.
- Entre a borda e a máquina da API, o `cloudflared` mantém um túnel criptografado; o último trecho é `127.0.0.1` dentro da própria máquina.
- O ESP32 continua em HTTP com HMAC até a borda (decisão D17). Esse trecho tem integridade e autenticidade, mas **não tem sigilo**. A limitação está declarada no README.

### 2.4 Falha e recuperação

| Passo | Resultado esperado | Registro |
|---|---|---|
| Wokwi, tecla `f` (queda de rede do ESP32) | ESP32 em modo local, com o alerta local se a FC estiver alta; o app mostra `DADOS_INSUFICIENTES` e o dispositivo sem contato | Serial "MODO LOCAL" às 19:09:23 com FC 136 em repouso; app "Sem leituras suficientes" e "Sem contato" ([`c08-esp32-sem-rede`](evidencias/app/completo/c08-esp32-sem-rede.png)) |
| Wokwi, tecla `f` de novo (rede volta) | Lotes voltam com HTTP 200; o estado é recalculado | `ATENCAO` de novo às 19:10:45, com o botão de volta e sem o reconhecimento do alerta anterior ([`c09-recuperado`](evidencias/app/completo/c09-recuperado.png)) |
| Celular em modo avião por cerca de 10 s | O app mostra o erro de rede e mantém o último estado na tela; o envio do movimento falha | Wi-Fi e dados desligados: "Sem conexão. Mostrando o último estado recebido." em 3 s; o sensor mostra a falha de envio ([`c15-celular-sem-rede`](evidencias/app/completo/c15-celular-sem-rede.png)) |
| Desligar o modo avião | O app volta a atualizar sozinho em até 2 s, sem novo login | Voltou em 3 s (o tempo inclui a leitura da tela pelo roteiro), sem novo login ([`c16-rede-voltou`](evidencias/app/completo/c16-rede-voltou.png)) |
| Parar a API por cerca de 10 s e iniciá-la de novo | O app mostra erro de rede; ao voltar, retoma com o mesmo token (válido por 8 h). O estado corrente recomeça vazio (pendência declarada) | Com a mesma `APP_SECRET_KEY`: erro em 3 s ([`c13-api-parada`](evidencias/app/completo/c13-api-parada.png)); de volta 3 s depois de a API subir, sem login, em "Sem leituras suficientes" ([`c14-api-voltou`](evidencias/app/completo/c14-api-voltou.png)) e "Tudo bem" 20 s depois ([`c14b-estado-reconstruido`](evidencias/app/completo/c14b-estado-reconstruido.png)) |

### Defeitos encontrados no ensaio completo

| Defeito | Como apareceu | Correção |
|---|---|---|
| Relógio do ESP32 atrasado no Wokwi | Depois de ~3 min, lotes e busca de comando recusados com 401; o reconhecimento levou 4 min 40 s para chegar ao ESP32 | D35: o ESP32 corrige o relógio pelo cabeçalho `Date` da API; o comando passou a ser executado 9 s depois do toque |
| ESP32 "Sem contato" entre dois lotes normais | O `online` usava 10 s fixos, e o Wokwi lento manda lotes a cada 8–13 s | O `online` usa o limite adaptativo do silêncio (D32); teste `test_online_acompanha_o_ritmo_dos_lotes` |
| Reconhecimento antigo num alerta novo | Depois da queda de rede, o alerta novo mostrava "Alarme silenciado no dispositivo", do alerta anterior | O app compara a criação do comando com o início do estado; 4 testes em `ComandoDoAlertaTest` |
| URL apagada depois da sessão expirada | Ao voltar ao login, o campo do servidor voltava a `https://` | URL e usuário ficam no `ViewModel`, que sobrevive à troca de tela |

O ensaio também encontrou falhas de DNS na rede da máquina (o `cloudflared` registrou *lookup timeout* e o emulador não resolveu o túnel uma vez). Esse é o motivo de o NTP do ESP32 não corrigir o relógio. Não houve mudança no código por isso.

## 3. O que não é verificado automaticamente

| Item | Situação | Impacto |
|---|---|---|
| TimescaleDB real no CI | Coberto com banco simulado; o banco real foi verificado no ensaio (2.2) | Um erro de SQL só aparece no ensaio |
| Celular físico | O app foi verificado no emulador; o acelerômetro e a rede de um aparelho real não foram testados (decisão do grupo) | Diferenças de sensor, fabricante ou rede móvel não foram observadas |
| Testes instrumentados do app | A lógica do app tem 23 testes de unidade; a interface (Compose) só é verificada no ensaio (2.0, 2.1, 2.3, 2.4) | Regressões de layout dependem de teste manual |
| TLS no ESP32 | Não implementado (D17) | Leituras sintéticas podem ser lidas no caminho |
| Recuperar o estado e o comando pendente depois de reiniciar a API | Não implementado | Depois do reinício, o estado recomeça vazio até chegarem novos lotes |

Os itens estão declarados como limitações ou pendências no [README](../README.md#limitações-e-pendências).
