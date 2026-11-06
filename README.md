# Internet dos Coisos · UFG · Software para Sistemas Ubíquos

**Marco 3 — monitoramento ubíquo demonstrativo com ESP32 virtual, processamento de eventos e histórico temporal.**

O sistema simula o acompanhamento de **frequência cardíaca (FC)** e **movimento** por uma roupa inteligente. Um ESP32 virtual no [Wokwi](https://wokwi.com/projects/478071248037862401) envia leituras assinadas para uma API Python; a API organiza os lotes em uma **fila FIFO**, calcula estados, persiste eventos no **TimescaleDB** e atualiza o painel do cuidador por **WebSocket**. O cuidador também pode reconhecer um alerta, produzindo um comando consumido e confirmado pelo ESP32.

> **Escopo:** protótipo acadêmico com dados sintéticos, sem finalidade diagnóstica, médica ou clínica. Não introduza dados de pacientes reais.

## Equipe

- Felipe Alves — 202105026
- Felipe O Carvalho — 202011561
- Matheus Augusto — 202305532
- Murilo Bernardo — 202203524

## O que compõe o Marco 3

| Componente | Papel na arquitetura | Onde está implementado |
|---|---|---|
| ESP32 virtual | Produz leituras e atua no LED/buzzer; consome comandos | [`marco3/produtor/`](marco3/produtor/) |
| HTTP + HMAC-SHA256 | Integra dispositivo e API com assinatura, timestamp e vínculo de identidade | [`marco3/api/app.py`](marco3/api/app.py) |
| Fila FIFO | Recebe lotes validados e delega a um consumidor único | `asyncio.Queue` em `app.py` |
| Regra de contexto | Calcula média móvel, cobertura, repouso, histerese e estado | [`marco3/api/regra.py`](marco3/api/regra.py) |
| TimescaleDB | Persiste leituras, mudanças de estado e histórico dos comandos | [`armazenamento.py`](marco3/api/armazenamento.py), [`temporal.py`](marco3/api/temporal.py) |
| WebSocket | Publica atualizações do estado ao painel autenticado | `app.py` e [`painel.html`](marco3/api/templates/painel.html) |
| Simulação de cenários | Normalidade, alerta, perda de sensor, movimento, falha/reconexão e ciclo automático | `sketch.ino` / Serial Monitor |

### Diagrama de arquitetura

![Arquitetura do Marco 3, com dois ciclos produtor-consumidor](marco3/docs/visuais/arquitetura-final.svg)

**Ciclo 1:** ESP32 → HTTP assinado → FastAPI → fila FIFO → `regra.py` → TimescaleDB e WebSocket → cuidador.

**Ciclo 2:** cuidador → comando de reconhecer alerta → FastAPI → ESP32 → silenciamento do buzzer → ACK → FastAPI → painel.

O **WebSocket conecta a API ao navegador**; o ESP32 mantém HTTP assinado. A fila `asyncio.Queue` é **volátil, em memória**; a persistência temporal é responsabilidade do TimescaleDB. As requisições HTTP do dispositivo aguardam o processamento do lote para manter o contrato de resposta com o estado calculado.

## Como executar no Windows / VS Code

Pré-requisitos: Python 3.10+, Git, acesso ao Wokwi e a um PostgreSQL com extensão TimescaleDB. A execução não depende de Docker. No **PowerShell, na raiz do repositório**:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r marco3\api\requirements-test.txt -r marco3\api\requirements-temporal.txt
.\.venv\Scripts\python.exe marco3\api\gerar_config.py
```

O gerador cria **arquivos privados ignorados pelo Git**: `marco3/api/.env` e `marco3/produtor/config.h`. Guarde a senha exibida para `cuidador01`. Adicione **somente no `.env` local** a URL real do serviço temporal com a chave `DATABASE_URL`, usando a string fornecida pelo provedor após a rotação de credenciais:

```dotenv
DATABASE_URL=postgresql://USUARIO:SENHA_URL_CODIFICADA@HOST:PORTA/BANCO?sslmode=require
```

Prepare e consulte o banco:

```powershell
.\.venv\Scripts\python.exe marco3\scripts\verificar_banco.py
```

Inicie a API:

```powershell
.\.venv\Scripts\python.exe marco3\api\app.py
```

Acesse **http://127.0.0.1:5000/login**. O painel usa uma sessão autenticada, atualiza por WebSocket e oferece um gráfico temporal de FC, métricas da fila, histórico e a ação **Reconhecer alerta**.

Para a comunicação do Wokwi, abra outro terminal e inicie o túnel:

```powershell
cloudflared tunnel --url http://127.0.0.1:5000
```

Copie a URL criada para `API_BASE_URL` em `marco3/produtor/config.h` e use esse arquivo **somente em uma cópia privada do Wokwi**, junto a `sketch.ino`, `diagram.json` e `libraries.txt`. Execute os cenários pelo Serial Monitor (`0`, `1`, `2`, `3`, `4`, `a`, `f`). A comunicação HTTP com HMAC foi mantida de acordo com a versão apresentada pelo grupo; **HMAC não criptografa o tráfego**.

**Procedimento integral, com comandos, SQL, portas, cenários, resultados esperados e diagnóstico:** [Guia único de execução e verificação](marco3/docs/GUIA_EXECUCAO_E_TESTES.md).

## Gráficos e decisões de contexto

O painel mostra **FC sintética em bpm versus tempo**, com descontinuidade em leituras inválidas. A linha de referência em 100 bpm não significa alerta instantâneo: a regra avalia **média das 10 últimas leituras**, cobertura mínima de 70%, repouso, duas avaliações consecutivas e histerese de saída abaixo de 92 bpm.

- [Gráficos, eixos, janelas, estados e diagramas explicados](marco3/docs/DIAGRAMAS_E_GRAFICOS.md)
- [Arquitetura editável em Mermaid](marco3/docs/arquitetura.mmd)
- [Esquema das três hypertables](marco3/api/sql/timescaledb.sql)

## Documentação do projeto

| Documento | Conteúdo |
|---|---|
| [Marco 3](marco3/README.md) | Requisitos, componentes, fluxos, rotas e limitações |
| [Execução e verificação](marco3/docs/GUIA_EXECUCAO_E_TESTES.md) | Instalação, banco, Wokwi, scripts, SQL e diagnóstico |
| [Diagramas e gráficos](marco3/docs/DIAGRAMAS_E_GRAFICOS.md) | Arquitetura, eventos, regra de contexto e leitura dos gráficos |
| [Roteiro de apresentação](marco3/docs/roteiro-apresentacao.md) | Demonstração de 10 minutos, com explicação de cada melhoria |
| [Origem da consolidação](marco3/docs/ORIGEM_CONSOLIDACAO.md) | Proveniência da `main`, `marco3-enxuto` e `timescaledb` |
| [Decisões de arquitetura](marco3/docs/decisoes.md) | Escolhas técnicas e limitações assumidas |
| [Marco 2](marco2/README.md) | Implementação e arquitetura anteriores (MQTT) |
| [Atividades 1 e 2](atividade-01.md) | Modelagem e fluxo conceitual; [Atividade 2](atividade-02.md) |

### Segurança e condições de operação

As chaves e URLs privadas **não são versionadas**. A API é executada com **um processo Uvicorn**, pois fila, estados e comandos pendentes ficam em memória. O banco guarda o histórico quando a conexão está disponível, mas não há reprocessamento durável de mensagens descartadas durante indisponibilidade. A janela temporal de HMAC reduz o replay antigo; não equivale a criptografia TLS nem impede todo replay dentro da janela.

O uso de IA generativa como apoio à programação e documentação está sujeito ao [Guia de Integridade Acadêmica da UFG](https://ufg.br/n/185267-nova-versao-do-guia-de-integridade-academica-traz-capitulo-sobre-ia), com revisão e responsabilidade dos integrantes.
