# Guia de execução e testes — Marco 3 consolidado

**Ambiente:** Windows 10/11, VS Code, PowerShell, Python 3.10+, Git, Wokwi e um serviço PostgreSQL com **TimescaleDB**. Não é necessário Docker. **Nenhum exemplo abaixo contém senha real.**

## 0. O que foi consolidado

- `main`: contrato HTTP assinado (HMAC), análise `regra.py`, dois ciclos produtor-consumidor e painel.
- `marco3-enxuto`: geração **privada** de `config.h` e `.env` com uma chave consistente, sem segredos versionados.
- `timescaledb`: `armazenamento.py` com gravação de **leituras**, **transições de estado** e **comandos**; com consulta ao histórico adicionada nesta consolidação.
- Melhoria integrada: **fila `asyncio.Queue`** (128 lotes), **WebSocket** autenticado no painel, cenários de simulação no firmware e testes.

**Arquitetura:** Wokwi ESP32 → HTTP POST assinado → FastAPI → FIFO (memória) → `regra.py` → TimescaleDB + WebSocket → painel. O ciclo de comando do cuidador ao ESP32 permanece via HTTP com ACK.

**Limitações:** fila não é durável, a API deve usar **um único processo de Uvicorn**, o estado corrente e o comando pendente ficam na memória; quando o banco cai, os registros não persistidos não são reenviados. A simulação de frequência cardíaca não representa sinais médicos reais. **HMAC não criptografa HTTP.** Não exponha dados sensíveis nem credenciais em um Wokwi público.

## 1. Clonar e abrir no VS Code

No VS Code, `Ctrl+Shift+P` → **Git: Clone** e cole:

```text
https://github.com/UFG-INF-SSU-2026/Internet-dos-Coisos.git
```

Abra a pasta clonada, depois **Terminal → New Terminal**, na **raiz do repositório**:

```powershell
git status
git branch --show-current
git remote -v
```

A URL `origin` deve apontar para a organização UFG. O repositório é mantido como versão oficial do grupo. As branches históricas permanecem preservadas.

## 2. Instalar Python e dependências (raiz do repositório)

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r marco3\api\requirements-test.txt -r marco3\api\requirements-temporal.txt
```

Se `py` não existir, instale Python 3.10+ e reinicie o terminal. As dependências incluem `websockets`, necessário para o upgrade HTTP/WebSocket no Uvicorn, e `psycopg[binary]`, para o TimescaleDB.

## 3. Gerar chaves privadas (raiz)

```powershell
.\.venv\Scripts\python.exe marco3\api\gerar_config.py
```

Na **primeira execução** cria:
- `marco3/api/.env` com segredo de sessão, chave da ESP32, hash de senha do cuidador.
- `marco3/produtor/config.h` com **a mesma chave** e URL do túnel a preencher na execução.

Guarde a senha exibida. Usuário do cuidador: `cuidador01`. Executar novamente preserva os arquivos existentes. Se faltar `config.h` e existir `.env`, o script o recompõe com a mesma chave. Se as duas chaves diferirem, o script aborta para evitar erro silencioso.

**Nunca comite** `.env`, `config.h`, credenciais de conexão, screenshots de senhas ou tokens. Ambos são ignorados por `.gitignore`. Cuidado: o projeto Wokwi também pode ficar público; não publique uma chave privada nele.

## 4. Criar TimescaleDB na nuvem (antes da demonstração completa)

### Opção recomendada: Tiger Cloud (sem Docker)

Documentação oficial: https://www.tigerdata.com/docs/get-started/quickstart/create-service

1. Crie uma conta em **https://console.tigerdata.com/** (ou pelo site oficial) e entre no painel.
2. Clique **New service**. Se estiver disponível, escolha **Shared / Free** (serviço gratuito em beta), selecionando PostgreSQL **com TimescaleDB**, não “plain PostgreSQL”. Confirme no resumo que o preço é zero. Se essa opção não estiver disponível, poderá aparecer avaliação gratuita de 30 dias de plano pago; avalie a continuidade e custos antes de aceitar.
3. Dê um nome como `ufg-internet-dos-coisos` e crie o serviço.
4. Baixe a **configuração de conexão** no momento da criação e guarde **fora do GitHub**. Ela contém host, porta, usuário, senha e banco. A senha pode ser exibida uma única vez.
5. No editor SQL do serviço, execute (ou confira):

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';
```

Se aparecer uma linha `timescaledb`, a extensão está habilitada. Este teste não deve ser confundido com PostgreSQL comum.

6. Abra `marco3/api/.env` (privado) e **acrescente ao fim** a URL que a própria plataforma forneceu, por exemplo:

```dotenv
DATABASE_URL=postgresql://USUARIO:SENHA_URL_ENCODED@HOST:5432/BANCO?sslmode=require
```

Não cole o exemplo literalmente. Se sua senha contiver `@`, `#`, `/`, `:` ou outros símbolos, use a URL **já formatada** pelo provedor, ou codifique a senha para URL. **Não compartilhe essa linha no chat, repositório ou screenshots.**

7. **Na raiz** do repositório, execute:

```powershell
.\.venv\Scripts\python.exe marco3\scripts\verificar_banco.py
```

O script verifica a extensão, cria/verifica três hypertables e conta os registros, sem mostrar a senha. Esperado:

```text
[OK] TimescaleDB versao: ...
Hypertables: comandos, eventos_estado, leituras
[OK] leituras: 0 registro(s)
[OK] eventos_estado: 0 registro(s)
[OK] comandos: 0 registro(s)
```

**As tabelas são criadas automaticamente** na primeira conexão com sucesso, pelo `armazenamento.py`. Alternativamente, execute manualmente `marco3/api/sql/timescaledb.sql` no editor SQL. Não é necessário executar duas vezes.

### Consultas SQL para a apresentação

```sql
SELECT hypertable_name FROM timescaledb_information.hypertables
WHERE hypertable_name IN ('leituras', 'eventos_estado', 'comandos')
ORDER BY hypertable_name;

SELECT count(*) AS total_leituras FROM leituras;
SELECT ts, lote_id, fc, g FROM leituras ORDER BY ts DESC LIMIT 10;
SELECT ts, estado, razao FROM eventos_estado ORDER BY ts DESC LIMIT 10;
SELECT ts, command_id, status FROM comandos ORDER BY ts DESC LIMIT 10;
```

**Comprovação de persistência:** envie leituras, observe o total aumentar, encerre e reinicie a API (sem excluir o banco), rode o script/SQL novamente e confirme que o total não voltou a zero. Os dados são de demonstração, portanto não correspondem a sinais vitais reais.

### Erros de banco

- `DATABASE_URL ausente`: adicione a linha ao arquivo privado `.env`.
- `connection timeout`: verifique internet, DNS, proxy, firewall e acesso ao servidor na porta do provedor (normalmente 5432); em PowerShell, `Test-NetConnection SEU_HOST -Port 5432`.
- `password authentication failed`: confira usuário e senha; evite caracteres não codificados na URL.
- `extension timescaledb is not available`: o servidor não tem TimescaleDB instalado; criar banco em PostgreSQL comum não resolve.
- `permission denied`: veja permissões de extensão/schema no provedor.
- `banco_ativo=false`: pode significar que a API ainda não fez a primeira consulta ou gravação. Envie um lote e repita `/api/saude`.
- Se o banco parar, a API funciona em memória, **mas perde as gravações do intervalo**. O verificador explicita a situação.

## 5. Iniciar a API (Terminal 1, raiz)

```powershell
.\.venv\Scripts\python.exe marco3\api\app.py
```

Abra http://127.0.0.1:5000/login e entre com `cuidador01` + senha gerada na etapa 3. Em outro navegador/terminal, teste:

```powershell
curl.exe -i http://127.0.0.1:5000/api/saude
```

Esperado HTTP 200 com JSON indicando `servico: online`. A URL `/api/saude` não expõe dados do paciente, credenciais ou senha.

### Diagnóstico do WebSocket

Se o Uvicorn mostrar `Unsupported upgrade request` ou `No supported WebSocket library detected`, o ambiente Python não instalou a dependência necessária. Na raiz do projeto, com a API encerrada, execute:

```powershell
.\.venv\Scripts\python.exe -m pip install -r marco3\api\requirements-test.txt -r marco3\api\requirements-temporal.txt
```

Depois reinicie a API. O projeto declara `websockets` em `requirements.txt`; isso não modifica a comunicação HTTP/HMAC da ESP32.

## 6. Testar API/fila/WebSocket sem Wokwi (Terminal 2, raiz)

O script assina lotes fictícios usando a chave privada local, por isso é útil quando a simulação não conecta:

```powershell
.\.venv\Scripts\python.exe marco3\scripts\simular_sem_wokwi.py
```

Abra o painel logado para observar o WebSocket atualizado; verifique no painel os contadores `enfileirados`, `processados` e `ultimosLotesProcessados` em ordem FIFO. Para ver fila temporariamente ocupada na demonstração, encerre a API e acrescente `QUEUE_DEMO_DELAY_MS=500` no `.env`, depois reinicie. **Remova este atraso antes do teste normal.**

Rota protegida do histórico, disponível somente após login:

```text
GET /api/pacientes/patient-0042/historico
```

Em modo banco, a resposta tem `origem: TimescaleDB`; em modo sem banco, indica memória não persistente. O WebSocket fica em `/ws/pacientes/patient-0042` e usa a sessão autenticada do navegador. O ESP32 **não** utiliza WebSocket: continua com HTTP/HMAC.

## 7. Conectar Wokwi usando Cloudflare (Terminal 3, raiz)

Se não tiver cloudflared:

```powershell
winget install --id Cloudflare.cloudflared
```

Feche e reabra o terminal, se necessário. Com a API funcionando no Terminal 1:

```powershell
cloudflared tunnel --url http://127.0.0.1:5000
```

Deixe o processo aberto. O túnel costuma imprimir uma URL como `https://abc.trycloudflare.com` (endereço **temporário**, muda ao reiniciar).

Teste primeiro com a URL pública fornecida (HTTPS no seu navegador):

```powershell
curl.exe -i https://abc.trycloudflare.com/api/saude
```

No projeto Wokwi https://wokwi.com/projects/478071248037862401 (ou um projeto privado do grupo), atualize **quatro** arquivos a partir de `marco3/produtor/`:

- `sketch.ino`
- `diagram.json`
- `libraries.txt`
- `config.h` **gerado localmente**, sem publicá-lo em projeto público

No `config.h` do Wokwi, atualize `API_BASE_URL` para **a URL do túnel atual com `http://`**, pois esse sketch foi testado assim pelo grupo. Exemplo ilustrativo:

```cpp
const char* API_BASE_URL = "http://abc.trycloudflare.com";
```

**Não use `BASE_URL`; o nome é `API_BASE_URL`.** Não acrescente `/api/leituras` à URL-base. **A troca de `https://` por `http://` é específica do sketch/teste anterior**, não uma recomendação de produção: HTTP com HMAC garante integridade/autenticidade, mas não sigilo. Se o túnel redirecionar HTTP para HTTPS ou o Wokwi não conectar, revise essa decisão; para produção, use HTTPS real.

Inicie a simulação e abra o **Serial Monitor**. Esperado `lote N: HTTP 200`, atualização em tempo real do painel e aumento do total em `leituras`.

### Modos de simulação (Serial Monitor do Wokwi)

| Tecla | Comportamento esperado |
|---|---|
| `1` | frequência normal |
| `2` | frequência alta em repouso, gerando ATENCAO após confirmação |
| `3` | ausência de FC válida, gerando DADOS_INSUFICIENTES |
| `4` | frequência alta com movimento |
| `a` | cenário automático de alternância |
| `f` | queda simulada de conexão |

Para o **segundo ciclo**, no cenário de alerta clique **Reconhecer alerta** no painel; o ESP32 consulta comando, silencia o buzzer e devolve ACK. O banco deve registrar `PENDENTE`, `ENTREGUE`, `EXECUTADO` em `comandos`.

### Erros do Wokwi

- `HTTP -1`: URL inválida, DNS/túnel inacessível ou problema de rede TLS/HTTP.
- `HTTP 401`: horário NTP não sincronizado, assinatura HMAC inválida, diferença de chaves, método/rota divergentes.
- `HTTP 403`: `deviceId`/`entityId` não autorizados.
- `HTTP 307/308`: redirecionamento; verifique o comportamento HTTP/HTTPS do túnel.
- `HTTP 200`: lote aceito. Veja `/api/saude`, painel e script do banco para confirmar o restante.

## 8. Testes automatizados Python (raiz)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s marco3\testes -v
```

A suíte verifica regras, login, assinaturas, fila, WebSocket, comandos e adaptador de persistência com objetos simulados. A execução da aplicação, do banco e do Wokwi é descrita nas seções anteriores.

## 9. Sequência de verificação reproduzível

Consulte o [protocolo de execução](CHECKLIST_ENTREGA.md) para percorrer preparação, banco, WebSocket, filas, cenários e segundo ciclo com ACK em uma ordem padronizada. O [roteiro de 10 minutos](roteiro-apresentacao.md) mostra a sequência de apresentação; [diagramas e gráficos](DIAGRAMAS_E_GRAFICOS.md) explicam como interpretar os indicadores e os estados.

## 10. Versionamento no repositório do grupo

A entrega é registrada na `main` da organização UFG, e `feat/marco3-consolidado` pode ser mantida apontando para o mesmo commit de referência. As branches `marco3-enxuto` e `timescaledb` permanecem preservadas como fontes históricas. Não publique arquivos privados; confirme o conteúdo dos arquivos antes do commit:

```powershell
git status --short
git diff --check
# Remover do indice a chave versionada antiga, preservando seu config.h local:
git rm --cached --ignore-unmatch -- marco3/produtor/config.h
git add -A -- README.md LEIA_PRIMEIRO_MARCO3_MELHORIAS.md marco3 .gitignore
git diff --cached --name-status
git diff --cached --check
# O comando abaixo nao pode listar config.h:
git ls-files --cached -- marco3/api/.env marco3/produtor/config.h
```

A origem e os limites da consolidação estão em [ORIGEM_CONSOLIDACAO.md](ORIGEM_CONSOLIDACAO.md).
