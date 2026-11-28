# Implantação do Marco 4

Este guia instala, configura e executa todos os componentes: banco temporal, API, túnel, ESP32 no Wokwi e app Android.
Os comandos são para **PowerShell, na raiz do repositório**. O [guia detalhado do Marco 3](GUIA_EXECUCAO_E_TESTES.md) continua valendo para diagnóstico de banco, Wokwi e WebSocket.

> **Nenhum segredo está no Git.** `marco4/api/.env` e `marco4/produtor/config.h` são gerados localmente e ficam no `.gitignore`. O APK não contém chave nenhuma.

## 1. Componentes e versões

| Componente | Versão usada | Observação |
|---|---|---|
| Python | 3.10 ou mais novo (o CI roda 3.10 e 3.12) | Usado pela API, pelos scripts e pelos testes |
| FastAPI / Starlette | `fastapi>=0.110,<1` (testado com 0.165) | `marco4/api/requirements.txt` |
| Uvicorn + websockets | `uvicorn>=0.25,<1`, `websockets>=12,<17` | Um único processo (fila e estado em memória) |
| itsdangerous | 2.x | Assina o cookie do painel e o token do app |
| psycopg | `psycopg[binary]>=3.2,<4` | Só para o TimescaleDB (`requirements-temporal.txt`) |
| pytest | `>=8,<10` | Só para gerar o relatório JUnit (`requirements-test.txt`) |
| PostgreSQL + TimescaleDB | Tiger Cloud (serviço gerenciado) com a extensão `timescaledb` | Qualquer PostgreSQL com TimescaleDB serve |
| cloudflared | 2026.10.1 | Túnel rápido `trycloudflare.com`, com HTTPS válido |
| ESP32 | Wokwi, ESP32 DevKit + MPU6050 | Bibliotecas em `marco4/produtor/libraries.txt` |
| Android Studio | JDK embutido (`jbr`), SDK Platform 37 e build-tools 36 | Gradle 9.9.3 (wrapper), AGP 9.5.3, plugin Compose 2.4.21, Compose BOM 2026.09.00 |
| Android (celular) | Android 8.0 ou mais novo (minSdk 26, targetSdk 37) | Precisa de acelerômetro e acesso à internet |

## 2. Preparar o ambiente Python

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r marco4\api\requirements-test.txt -r marco4\api\requirements-temporal.txt
```

## 3. Credenciais de teste

**Opção A, recomendada se o Marco 3 já roda na máquina:** reaproveite as credenciais e a `DATABASE_URL` do Marco 3. Assim o Wokwi continua com a mesma chave.

```powershell
Copy-Item marco3\api\.env marco4\api\.env
.\.venv\Scripts\python.exe marco4\api\gerar_config.py   # recria marco4/produtor/config.h com a MESMA chave
```

**Opção B, ambiente novo:**

```powershell
.\.venv\Scripts\python.exe marco4\api\gerar_config.py
```

O script mostra a senha do cuidador **uma única vez**. Guarde-a fora do Git.

| Identidade | Valor | Onde fica | Papel |
|---|---|---|---|
| Cuidador (painel e app) | usuário `cuidador01`, senha gerada | `.env` guarda só o hash scrypt (`CUIDADOR_SENHA_HASH`) | Vê o paciente `patient-0042` e reconhece alertas |
| Dispositivo | `esp32-borda-01` + `DEVICE_API_KEY` | `.env` e `produtor/config.h` | Publica leituras por `patient-0042`, recebe comandos e envia ACK |
| Paciente fictício | `patient-0042` | `.env` (`PATIENT_ID`) | Vínculo usado na autorização (403 para qualquer outro) |
| Segredo do servidor | `APP_SECRET_KEY` | `.env` | Assina o cookie do painel e o token do app |

Para **definir uma senha de teste conhecida** (por exemplo, para o professor reproduzir a execução), gere o hash e troque a linha `CUIDADOR_SENHA_HASH` no `.env`:

```powershell
.\.venv\Scripts\python.exe -c "import hashlib,secrets,getpass; s=secrets.token_bytes(16); p=getpass.getpass('Senha: '); print('CUIDADOR_SENHA_HASH=scrypt$'+s.hex()+'$'+hashlib.scrypt(p.encode(),salt=s,n=2**14,r=8,p=1).hex())"
```

A chave do ESP32 que ficou versionada em 16/10 (commit `b419733`) foi removida do Git em 06/11 (`f59a370`). A chave em uso é outra, gerada por `gerar_config.py`.

## 4. Ordem de execução

Execute nesta ordem. Os passos 2 e 3 ficam com terminais abertos.

| Ordem | Componente | Comando ou ação | Como saber que funcionou |
|---|---|---|---|
| 1 | Banco TimescaleDB | Criar o serviço e colocar `DATABASE_URL` no `.env` (seção 5) → `.\.venv\Scripts\python.exe marco4\scripts\verificar_banco.py` | `[OK] TimescaleDB versao` e as 3 hypertables |
| 2 | API (Terminal 1) | `.\.venv\Scripts\python.exe marco4\api\app.py` | `curl.exe http://127.0.0.1:5000/api/saude` devolve `"versao": "4.0"` e `"banco_configurado": true` |
| 3 | Túnel (Terminal 2) | `cloudflared tunnel --url http://127.0.0.1:5000` | Mostra `https://<nome>.trycloudflare.com`; `curl.exe https://<nome>.trycloudflare.com/api/saude` devolve 200 |
| 4 | ESP32 no Wokwi do VS Code | Em `config.h`, `API_BASE_URL = "http://host.wokwi.internal:5000"`; depois `pio run` em `marco4/produtor` e **F1 → Wokwi: Start Simulator** (abaixo) | Serial Monitor mostra `lote N: HTTP 200` |
| 5 | App Android | Instalar `marco4/apk/coisos-cuidador.apk` (seção 6), informar `https://<nome>.trycloudflare.com`, `cuidador01` e a senha | Tela principal mostra "Tudo bem" ou "Atenção" e o dispositivo "Conectado" |
| 6 | Painel web (opcional) | http://127.0.0.1:5000/login | Gráfico e estado atualizando por WebSocket |

A URL do túnel muda a cada vez que o `cloudflared` reinicia. Quando mudar, atualize a URL na tela de login do app.

> **Por que o ESP32 não usa o túnel (D33):** desde 27/11/2026 o túnel rápido responde `301` a todo `http://`, e o sketch não completa HTTPS (D17). Pelo Wokwi do VS Code, o ESP32 alcança a API da própria máquina em `host.wokwi.internal`, e o tráfego não sai do computador. O projeto no wokwi.com só funcionaria com HTTPS no sketch.

**Wokwi no VS Code (alternativa ao wokwi.com, exige a licença da extensão):**
1. Com o PlatformIO instalado, rode `pio run` em `marco4/produtor`. O firmware sai em `.pio/build/esp32/`.
2. Abra a pasta `marco4/produtor` no VS Code e escolha **F1 → Wokwi: Start Simulator**. O `wokwi.toml` aponta para o firmware e usa o mesmo `diagram.json`.
3. A serial também fica disponível em `rfc2217://localhost:4000`, para scripts enviarem as teclas e lerem o log.
4. O sensor de pulso é um chip próprio (D34). O `wokwi.toml` carrega o `sensor-pulso.chip.wasm` já compilado. Quem mudar o `sensor-pulso.chip.c` recompila com o WASI SDK (comando no topo do arquivo) e **reinicia o simulador**: só assim o Wokwi relê o chip e o `diagram.json`. No wokwi.com, o chip é compilado na nuvem a partir do `.c` e do `.json`, que devem ser adicionados ao projeto.

Sem o Wokwi, o script `.\.venv\Scripts\python.exe marco4\scripts\simular_sem_wokwi.py` faz o papel do ESP32 e assina os lotes com a chave local.

## 5. Configurar o armazenamento

1. Crie um serviço PostgreSQL **com TimescaleDB** (o passo a passo do Tiger Cloud está no [guia do Marco 3, seção 4](GUIA_EXECUCAO_E_TESTES.md#4-criar-timescaledb-na-nuvem-antes-da-demonstração-completa)).
   Alternativa local, usada no ensaio completo de 27/11/2026: `docker run -d --name coisos-tsdb -p 127.0.0.1:5433:5432 -e POSTGRES_PASSWORD=<senha> -e POSTGRES_DB=coisos timescale/timescaledb:latest-pg17`, com `DATABASE_URL=postgresql://postgres:<senha>@127.0.0.1:5433/coisos`. O driver vem de `api/requirements-temporal.txt`.
2. Acrescente ao `marco4/api/.env` a URL fornecida pelo provedor:
   ```dotenv
   DATABASE_URL=postgresql://USUARIO:SENHA_URL_CODIFICADA@HOST:PORTA/BANCO?sslmode=require
   ```
3. Rode `.\.venv\Scripts\python.exe marco4\scripts\verificar_banco.py`. A API também cria as tabelas sozinha na primeira conexão. Se preferir criar manualmente, o esquema está em [`api/sql/timescaledb.sql`](../api/sql/timescaledb.sql).

| Hypertable | O que guarda |
|---|---|
| `leituras` | Cada leitura do ESP32 (`ts`, `patient_id`, `device_id`, `lote_id`, `fc`, `g`) |
| `eventos_estado` | Cada transição de estado com razão, média de FC e movimento, inclusive `movimento_no_celular` |
| `comandos` | `PENDENTE → ENTREGUE → EXECUTADO` de cada reconhecimento de alerta |

Para comprovar a persistência depois de reiniciar a API:

```sql
SELECT count(*) FROM leituras;
SELECT ts, estado, razao FROM eventos_estado ORDER BY ts DESC LIMIT 10;
SELECT ts, command_id, status FROM comandos ORDER BY ts DESC LIMIT 10;
```

Sem `DATABASE_URL`, a API funciona só em memória, e `/api/saude` mostra `"banco_configurado": false`.

## 6. Compilar e instalar o app

O passo a passo completo está em [`../mobile/README.md`](../mobile/README.md). Em resumo:

1. Android Studio → **Open** → `marco4/mobile` e aguarde o *Gradle sync*.
2. **Build → Build APK(s)**. O arquivo sai em `marco4/mobile/app/build/outputs/apk/debug/app-debug.apk`.
3. Copie-o para `marco4/apk/coisos-cuidador.apk`.
4. Para instalar, há duas opções:
   - com o celular ligado por USB e a depuração USB ativa, rode `adb install -r marco4\apk\coisos-cuidador.apk`;
   - ou copie o APK para o celular e abra-o, autorizando "instalar apps desconhecidos".

O app só aceita URL `https://`. O Android valida o certificado do túnel com as CAs do sistema, sem exceção e sem certificado embutido.

## 7. Rodar os testes automatizados

```powershell
cd marco4\testes
..\..\.venv\Scripts\python.exe -m pytest -v --junitxml=relatorio-junit.xml test_regra.py test_api.py test_melhorias.py test_consolidacao.py test_app_mobile.py
# ou, sem pytest:
..\..\.venv\Scripts\python.exe -m unittest -v test_regra test_api test_melhorias test_consolidacao test_app_mobile
```

O que cada módulo cobre e os resultados registrados estão em [`verificacao.md`](verificacao.md). O CI (`.github/workflows/testes.yml`) roda a mesma suíte a cada push na `main` e guarda o relatório JUnit como artefato.

## 8. Encerrar

Pare o app, depois o Wokwi, o túnel (`Ctrl+C`) e a API (`Ctrl+C`). O banco continua com os dados. Na próxima execução, repita a partir do passo 2 da seção 4.
