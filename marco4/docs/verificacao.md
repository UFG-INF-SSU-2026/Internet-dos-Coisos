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

**Resultado registrado:** 44 testes aprovados.
- Execução local: [`evidencias/testes-api.txt`](evidencias/testes-api.txt), com Python 3.14 no commit `a94e70b`.
- CI no GitHub Actions: roda a cada push na `main`, com Python 3.10 e 3.12 ([histórico de execuções](https://github.com/UFG-INF-SSU-2026/Internet-dos-Coisos/actions/workflows/testes.yml)). A primeira execução, com 42 testes, foi o [run 46039476817](https://github.com/UFG-INF-SSU-2026/Internet-dos-Coisos/actions/runs/46039476817) no merge `6f1a443`. Os relatórios JUnit ficam nos artefatos `relatorio-junit-py3.10` e `relatorio-junit-py3.12`.

### Módulos e requisitos cobertos

| Arquivo de teste | Módulo exercitado | Requisito coberto | Testes |
|---|---|---|---|
| `test_regra.py` | `api/regra.py` | Regra com estado e tempo: janela, cobertura, persistência, histerese, silêncio | 7 |
| `test_api.py` | `api/app.py` (rotas do ESP32 e do painel) | Autenticação HMAC, autorização dispositivo/paciente/cuidador, ciclo 1 e ciclo 2 | 12 |
| `test_melhorias.py` | `app.py` (fila, WebSocket, histórico) | Fila FIFO, WebSocket autenticado, `/api/saude` sem dados pessoais | 6 |
| `test_consolidacao.py` | `app.py` + `temporal.py` + `gerar_config.py` | Gravação de leituras, transições e comandos; consulta do histórico; segredos fora do Git | 4 |
| `test_app_mobile.py` | `app.py` (rotas do app) + `regra.py` (contexto) | Token do app, segundo produtor, validade e atraso, mudança de contexto, ciclo 2 pelo app | 15 |

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

## 3. O que não é verificado automaticamente

| Item | Situação | Impacto |
|---|---|---|
| TimescaleDB real no CI | Coberto com banco simulado; o banco real só no ensaio (2.2) | Um erro de SQL só aparece no ensaio |
| Testes instrumentados do app | Não há; a interface é verificada no ensaio (2.1, 2.3, 2.4) | Regressões de tela dependem de teste manual |
| TLS no ESP32 | Não implementado (D17) | Leituras sintéticas podem ser lidas no caminho |
| Recuperar o estado e o comando pendente depois de reiniciar a API | Não implementado | Depois do reinício, o estado recomeça vazio até chegarem novos lotes |

Os quatro itens estão declarados como pendências para 11/12 no [README](../README.md#limitações-e-pendências).
