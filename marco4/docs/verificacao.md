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

**Resultado registrado:** 49 testes aprovados.
- Execução local: [`evidencias/testes-api.txt`](evidencias/testes-api.txt), com Python 3.14 no commit `b33f7a1`. Os 5 testes novos cobrem o silêncio adaptativo (D32).
- CI no GitHub Actions: roda a cada push na `main`, com Python 3.10 e 3.12 ([histórico de execuções](https://github.com/UFG-INF-SSU-2026/Internet-dos-Coisos/actions/workflows/testes.yml)). A primeira execução, com 42 testes, foi o [run 46039476817](https://github.com/UFG-INF-SSU-2026/Internet-dos-Coisos/actions/runs/46039476817) no merge `6f1a443`. Os relatórios JUnit ficam nos artefatos `relatorio-junit-py3.10` e `relatorio-junit-py3.12`.

### Módulos e requisitos cobertos

| Arquivo de teste | Módulo exercitado | Requisito coberto | Testes |
|---|---|---|---|
| `test_regra.py` | `api/regra.py` | Regra com estado e tempo: janela, cobertura, persistência, histerese, silêncio (fixo e adaptativo) | 12 |
| `test_api.py` | `api/app.py` (rotas do ESP32 e do painel) | Autenticação HMAC, autorização dispositivo/paciente/cuidador, ciclo 1 e ciclo 2 | 12 |
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

**Resultado registrado:** 15 testes aprovados.
- Execução local: [`evidencias/testes-app.txt`](evidencias/testes-app.txt).
- CI: job `app-android` do mesmo workflow. Roda os testes, gera o APK e guarda os artefatos `relatorio-junit-app` e `coisos-cuidador-debug-apk`.

### Complemento do PR #6 (execução no CI pendente)

Foram acrescentados os seguintes testes; os resultados definitivos devem ser atualizados após o GitHub Actions desta branch:
- `test_regra.py`: restauração da janela, estado, histórico e intervalos do silêncio adaptativo.
- `test_consolidacao.py`: reinício da API com snapshot persistido e comando `PENDENTE`.
- `test_temporal_real.py`: gravação, consulta e recuperação de leituras, transições e status do comando contra TimescaleDB real. Localmente, requer `DATABASE_URL`; no CI, usa `timescale/timescaledb:latest-pg17`.
- Android: 3 novos testes JVM e 2 testes instrumentados Compose para login e recusa de URL incompleta.

O estado restaurado usa até 10 leituras recentes, até 20 transições e o registro de status mais recente do comando. Movimento do celular, fila FIFO e contadores da sessão não são restaurados. Se o banco estiver indisponível, a API inicia em memória vazia.

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

Esta parte é preenchida pelo grupo durante o ensaio, com o sistema completo: TimescaleDB, API, túnel, Wokwi e o APK instalado no celular.
Na coluna **Registro**, anote o resultado observado e o trecho do vídeo, print ou consulta SQL que serve de evidência. Oculte senhas, tokens e a `DATABASE_URL`.

Versão ensaiada: commit `________`, APK `coisos-cuidador.apk` (SHA-256 `________`), Android `____`, data `__/__/2026`.

### 2.0 Ensaio preliminar no emulador (27/11/2026)

Antes do ensaio com o celular, o APK foi testado no emulador do Android Studio (Medium Phone, Android API 37, 1080×2400).
- **API:** a versão deste commit, com credenciais temporárias e **sem banco**, exposta por um túnel `trycloudflare.com` real (HTTPS).
- **ESP32:** substituído por um script que envia lotes assinados com HMAC a cada 3 s (FC 120 bpm, `g = 1.0`), busca o comando e devolve o ACK. Log em [`evidencias/ensaio-emulador-esp32-sim.txt`](evidencias/ensaio-emulador-esp32-sim.txt).
- **Movimento:** simulado com `adb emu sensor set acceleration`.
- **Prints:** estão em [`evidencias/app/`](evidencias/app/).

Este ensaio **não substitui** os itens 2.1 a 2.4 com celular real, Wokwi e TimescaleDB.

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

Neste ensaio não foram verificados: o TimescaleDB (2.2), o certificado no navegador (2.3) e o celular físico.

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
| Entrar no app com `cuidador01` pela URL `https://…trycloudflare.com` | Tela de estado carrega; aparece "ESP32 online" | |
| Wokwi, tecla `1` (FC normal) | App e painel mostram `NORMAL` | |
| Wokwi, tecla `2` (FC alta em repouso), com o celular parado na mesa | `ATENCAO` em cerca de 10 s; LED e buzzer ligam; o botão **Reconhecer alerta** fica ativo | |
| Tocar **Reconhecer alerta** no app | Comando `PENDENTE → ENTREGUE → EXECUTADO`; o buzzer silencia e o LED continua aceso | |
| Ainda na tecla `2`, balançar o celular | Movimento com `fonte: celular`; alerta encerrado com `razao = movimento_no_celular` | |
| Parar de balançar | Depois de cerca de 6 s o contexto expira e a FC alta volta a gerar `ATENCAO` | |

### 2.2 Persistência

| Passo | Resultado esperado | Registro |
|---|---|---|
| Rodar o fluxo 2.1 e executar `SELECT count(*) FROM leituras;` | Contagem maior que zero | |
| Parar a API (`Ctrl+C`) e iniciá-la de novo | `/api/saude` mostra `banco_ativo` | |
| Repetir as consultas de `leituras`, `eventos_estado` e `comandos` | A contagem não volta a zero; aparecem a transição `movimento_no_celular` e o comando `EXECUTADO` | |
| `GET /api/pacientes/patient-0042/historico` (painel logado) | `origem: TimescaleDB` com as leituras anteriores ao reinício | |

### 2.3 Segurança

| Passo | Resultado esperado | Registro |
|---|---|---|
| Login no app com senha errada | Mensagem "Usuário ou senha incorretos" (401) | |
| `curl.exe -i -H "Authorization: Bearer invalido" https://…/api/pacientes/patient-0042/estado` | 401 | |
| Com um token válido, `GET /api/pacientes/patient-9999/estado` | 403 | |
| No app, digitar a URL com `http://` | O app recusa: "Use a URL https:// do túnel" | |
| Abrir a URL do túnel no navegador e ver o certificado | Certificado válido para `*.trycloudflare.com`, emitido por uma CA pública | |

**Canal:**
- O app fala HTTPS com a borda da Cloudflare, e o Android valida o certificado e o nome do serviço.
- Entre a borda e a máquina da API, o `cloudflared` mantém um túnel criptografado; o último trecho é `127.0.0.1` dentro da própria máquina.
- O ESP32 continua em HTTP com HMAC até a borda (decisão D17). Esse trecho tem integridade e autenticidade, mas **não tem sigilo**. A limitação está declarada no README.

### 2.4 Falha e recuperação

| Passo | Resultado esperado | Registro |
|---|---|---|
| Wokwi, tecla `f` (queda de rede do ESP32) | ESP32 em modo local, com o alerta local se a FC estiver alta; o app mostra `DADOS_INSUFICIENTES` e "ESP32 sem contato recente" | |
| Wokwi, tecla `f` de novo (rede volta) | Lotes voltam com HTTP 200; o estado é recalculado | |
| Celular em modo avião por cerca de 10 s | O app mostra "Erro de rede" e mantém o último estado na tela; o envio do movimento falha | |
| Desligar o modo avião | O app volta a atualizar sozinho em até 2 s, sem novo login | |
| Parar a API por cerca de 10 s e iniciá-la de novo | O app mostra erro de rede; ao voltar, retoma com o mesmo token (válido por 8 h). O estado corrente recomeça vazio (pendência declarada) | |

### 2.5 Recuperação após reinício com TimescaleDB

| Passo | Resultado esperado | Registro |
|---|---|---|
| Executar o fluxo 2.1 com banco ativo até entrar em `ATENCAO` | Transição e leituras do ESP32 gravadas no TimescaleDB | |
| Criar comando de reconhecimento, sem desligar o ESP32 antes da entrega/ACK | A tabela `comandos` registra `PENDENTE` ou `ENTREGUE` | |
| Reiniciar apenas a API, mantendo TimescaleDB ativo | Ao iniciar, API carrega janela recente, histórico e último status do comando (D35) | |
| Consultar `GET /api/pacientes/patient-0042/estado` | Estado volta como `ATENCAO`; comando pendente continua disponível para o ESP32 | |
| Permitir o GET do comando e ACK | O ESP32 executa e o estado persistido passa a `EXECUTADO` | |
| Reiniciar sem `DATABASE_URL` ou com banco indisponível | API inicia em memória vazia; não declara restauração que não aconteceu | |


## 3. O que não é verificado automaticamente

| Item | Situação | Impacto |
|---|---|---|
| TimescaleDB real no CI | Teste real adicionado no PR #6; o job usa um serviço TimescaleDB em contêiner. Aguardar execução verde | Exercita DDL, hypertables, gravação, consulta e restauração de dados |
| Testes instrumentados do app | Dois testes Compose adicionados no PR #6 e executados em emulador via Actions; aguardar CI | O ensaio manual em aparelho físico continua necessário para sensor e conectividade |
| TLS no ESP32 | Não implementado (D17) | Leituras sintéticas podem ser lidas no caminho |
| Recuperar o estado e o comando pendente depois de reiniciar a API | Implementação D35 + testes de unidade/integrados no PR #6; aguardar CI e ensaio com banco real | Restaura leituras, transições e último comando; fila FIFO e movimento do celular continuam voláteis |

Os quatro itens estão declarados como pendências para 11/12 no [README](../README.md#limitações-e-pendências).
