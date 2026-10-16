# Marco 3 — Comunicação HTTP, login e autenticação

**Disciplina:** Software para Sistemas Ubíquos · Instituto de Informática / UFG · 2026/2  
**Grupo:** Internet dos Coisos  
**Cenário:** monitoramento demonstrativo de sinais vitais de pessoas em situação de vulnerabilidade física por *smart clothing*.

> **Protótipo de graduação.** O potenciômetro simula a frequência cardíaca; os eventos **não são dados médicos reais** e o projeto não serve para diagnóstico ou acompanhamento clínico.

## 1. O que foi pedido e como atendemos

Requisitos do Marco 3: usar **HTTP / API REST**, incluir **login e autenticação** e definir uma forma de identificar quais produtores e consumidores são autorizados. A solução prioriza entendimento do fluxo em vez de adicionar serviços desnecessários.

| Conceito | Implementação escolhida |
|---|---|
| Produção na borda | ESP32 no Wokwi, programado em Arduino/C++ |
| Comunicação HTTP | `POST /api/eventos` e `POST /api/heartbeat`, por HTTPS |
| Ligação Wokwi → PC (gratuita) | Túnel HTTPS da Cloudflare (*Quick Tunnel*): sem conta, sem cartão |
| API REST intermediária | FastAPI (Python) — mesma linguagem do consumidor do Marco 2 |
| Autenticação do produtor | Chave `X-Device-Key`, cadastrada no servidor |
| Autenticação do cuidador | Usuário/senha, hash scrypt e cookie de sessão assinado |
| Autorização | A API vincula `esp32-borda-01` → `patient-0042` → `cuidador01` |
| Consumo | Painel HTML, atualização por `GET /api/pacientes/{id}/estado` |
| Falhas de comunicação | Fila de 12 eventos no ESP32, reenvio em ordem |
| Detecção de silêncio | `heartbeat` e identificação de ausência de contato recente |
| Banco e plataforma externa | **Não utilizados** nesta etapa: memória é suficiente para a demo |

**Neste Marco 3, a comunicação principal é HTTP/REST e não MQTT.** O código MQTT permanece intacto em `marco2/` como registro histórico da entrega anterior.

### Fluxo simplificado

```text
Potenciômetro + MPU6050
       │
       ▼
  ESP32 no Wokwi (gratuito)  ←→  LED e buzzer (decisão local)
       │
       │ HTTPS POST + chave individual (certificado validado)
       ▼
  Túnel Cloudflare  https://xxxx.trycloudflare.com   (gratuito)
       │
       ▼ (dentro do PC)
  API REST (FastAPI) em 127.0.0.1:5000 ── valida dispositivo/paciente ── guarda último evento
       ▲
       │ HTTP POST /login e GET /api/pacientes/.../estado
       │ sessão + autorização (no próprio PC)
       ▼
  Página web do cuidador
```

Diagrama editável: [`docs/arquitetura.mmd`](docs/arquitetura.mmd).

## 2. Estrutura dos arquivos

```text
marco3/
├── README.md                    ← este guia
├── produtor/
│   ├── sketch.ino               ← ESP32: sensores, regra, LED/buzzer e HTTPS POST
│   ├── diagram.json             ← circuito do Wokwi (um LED + buzzer)
│   ├── libraries.txt            ← bibliotecas do MPU6050
│   ├── certificados_raiz.h      ← certificados raiz públicos para validar o HTTPS
│   └── config.exemplo.h         ← formato da config; nunca publicar config.h
├── api/
│   ├── app.py                   ← API, login, proteção de rotas e memória
│   ├── gerar_config.py          ← gera credenciais coerentes no servidor e ESP32
│   ├── requirements.txt         ← dependências mínimas
│   ├── requirements-test.txt    ← inclui biblioteca para testes
│   ├── .env.exemplo             ← somente referência, não contém segredos reais
│   └── templates/
│       ├── login.html           ← formulário do cuidador
│       └── painel.html          ← últimas condições monitoradas
├── contrato/
│   └── evento-v2.json           ← exemplo de evento HTTP
├── docs/
│   └── arquitetura.mmd
└── testes/
    └── test_api.py             ← testes automatizados sem Wokwi
```

## 3. Executar a API e o login (Windows)

**Requisitos:** Python 3.10+ com `pip`, acesso ao terminal e navegador. O ESP32 simulado não roda Python: ele continua em **Arduino/C++**.

Abra o PowerShell na pasta **`marco3/api`** e execute:

```powershell
python -m pip install -r requirements.txt
python gerar_config.py
python app.py
```

O segundo comando **gera dois arquivos sincronizados**:

- `api/.env` — configura o servidor, hash da senha do cuidador e chave do dispositivo;
- `produtor/config.h` — mesma chave do dispositivo e endereço da API para o ESP32.

A senha aleatória do cuidador aparece no terminal **uma única vez**. Anote-a. Usuário padrão: `cuidador01`. Não suba `.env` ou `config.h` ao GitHub. Se precisar gerar novos segredos, remova **os dois arquivos** e execute `python gerar_config.py` novamente (o login e o Wokwi devem usar a mesma chave).

Abra no computador: **http://127.0.0.1:5000/login** e entre com o usuário e senha gerados. Antes de iniciar o ESP32, o painel mostra `SEM EVENTOS`.

> Se o terminal não reconhecer `python`, experimente `py`. Também é possível usar ambiente virtual, mas não é obrigatório para a aula.

## 4. Ligar o Wokwi à API do PC (caminho gratuito)

O Wokwi gratuito alcança a **internet**, mas não o `localhost` do seu computador. Por isso a API do PC recebe um endereço público temporário com o **Cloudflare Quick Tunnel**, que é gratuito e não exige conta nem cartão. Igual ao Marco 2: o ESP32 roda no Wokwi e o resto roda no terminal do PC.

**Instalar o túnel (uma vez):** no PowerShell, `winget install --id Cloudflare.cloudflared`. Feche e reabra o terminal.

**A cada demonstração:**

1. **Terminal 1** (pasta `marco3/api`): `python app.py`.
2. **Terminal 2**: `cloudflared tunnel --url http://127.0.0.1:5000`. Copie a URL `https://xxxx.trycloudflare.com` que aparecer no quadro.
   - Use `127.0.0.1`, não `localhost`: no Windows, `localhost` pode apontar para IPv6 e a API escuta só em `127.0.0.1`.
3. **Wokwi** (navegador, conta gratuita): crie um projeto ESP32 e coloque os arquivos de `marco3/produtor/`: `sketch.ino`, `diagram.json`, `libraries.txt`, `certificados_raiz.h` e o **`config.h` gerado** (botão de novo arquivo no editor, colando o conteúdo).
4. No `config.h` do Wokwi, troque `https://COLE-AQUI-A-URL-DO-TUNEL.trycloudflare.com` pela URL do passo 2. O Wokwi não precisa de nenhuma configuração de rede extra.
5. Inicie a simulação. No monitor serial devem aparecer `heartbeat: HTTP 200` e, nas mudanças de estado, `HTTP 201: evento entregue`.
6. **No próprio PC**, abra `http://127.0.0.1:5000/login` e entre como cuidador. Mexa no potenciômetro e acompanhe o painel.

A URL do túnel **muda toda vez** que o `cloudflared` é reiniciado. Nesse caso, atualize só a linha `API_BASE_URL` no `config.h` do Wokwi. Não deixe o projeto do Wokwi público com o `config.h`, que contém a chave do dispositivo.

**Por que HTTPS?** O tráfego do Wokwi gratuito passa por um gateway público compartilhado. O ESP32 abre uma conexão TLS até a Cloudflare e **valida o certificado** usando as raízes públicas de `certificados_raiz.h` (Let's Encrypt, Google Trust Services, SSL.com e Sectigo, as autoridades que a Cloudflare usa). Se o certificado não for válido, a conexão é recusada; o código nunca usa `setInsecure()`. Assim, a chave `X-Device-Key` e os eventos não trafegam abertos pela internet. Do túnel até a API, o tráfego fica dentro do PC.

**Se o monitor serial mostrar `HTTP falhou (-1)`:** confira se a API e o túnel estão abertos, se a URL no `config.h` é a atual e se a falha simulada (botão vermelho / tecla `f`) está desligada. Os eventos ficam na fila e são reenviados quando a conexão volta.

## 5. O que acontece quando o Wokwi produz uma alteração?

1. O potenciômetro simula FC (30–220 bpm plausíveis) e o MPU6050 indica repouso/movimento.
2. O ESP32 grava leituras em **janelas deslizantes**, calcula cobertura e média; sem cobertura de 70%, gera `DADOS_INSUFICIENTES`. Em repouso com FC média acima do limiar, persistência e histerese, pode gerar `ATENCAO`.
3. O LED (apagado = normal, aceso = atenção, piscando = dados insuficientes) e o buzzer respondem **localmente**, mesmo sem Internet.
4. Quando o estado muda, o ESP32 cria um JSON com `deviceId`, `entityId`, `bootId`, `sequence`, `eventId`, estado e resumo das leituras. **Não envia amostras brutas**, apenas transições de estado.
5. O ESP32 chama `POST /api/eventos` pela URL HTTPS do túnel, enviando o JSON e a chave em `X-Device-Key`.
6. A API verifica a chave, o vínculo com o paciente, o contrato v2 e a sequência. Guarda o último evento em memória.
7. O cuidador faz login e o navegador consulta `GET /api/pacientes/patient-0042/estado`, com cookie de sessão. A API verifica a permissão e retorna o último estado.

O `bootId` muda a cada reinício do ESP32: por isso a API consegue diferenciar `sequence=1` de uma nova simulação e `sequence=1` de uma simulação anterior. Duplicatas recentes retornam `200` sem contabilizar novo evento; eventos fora de ordem podem receber `409`.

### Endpoints e status HTTP

| Rota | Quem utiliza | Autenticação | Retorno esperado |
|---|---|---|---|
| `POST /api/eventos` | ESP32 | `X-Device-Key` e vínculo | `201` aceito, `200` duplicata, `400` inválido, `401` sem chave, `403` vínculo inválido, `409` fora de ordem |
| `POST /api/heartbeat` | ESP32 | `X-Device-Key` e vínculo | `200` contato recebido |
| `GET /login` / `POST /login` | Cuidador | Usuário, senha e proteção do formulário | HTML ou redirecionamento |
| `POST /logout` | Cuidador | Sessão e proteção do formulário | Redirecionamento |
| `GET /api/pacientes/{id}/estado` | Navegador | Sessão e vínculo do cuidador | `200`, `401` ou `403` |

A documentação automática das rotas REST fica em **http://127.0.0.1:5000/docs**. Ela descreve os endpoints, mas não substitui os exemplos e as verificações explicados aqui.

## 6. Testes para a apresentação

| Demonstração | O que observar |
|---|---|
| Abrir `/painel` sem login | Redireciona a `/login`; API responde `401` sem sessão |
| Tentar senha errada | O login retorna erro e não cria sessão |
| Entrar com credenciais certas | O painel é liberado |
| Alterar o potenciômetro e aguardar | ESP32 decide, LED acende, envia `POST`, API responde `201`, painel muda |
| Desligar a comunicação pelo botão vermelho GPIO13 ou teclar `f` | ESP32 continua decidindo; evento vai para fila e painel deixa de receber atualização |
| Reabilitar a comunicação | Fila é reenviada na ordem e painel atualiza |
| Enviar chave inválida ou tentar consultar outro paciente | API retorna `401` ou `403` |
| Reiniciar a simulação | Novo `bootId`; a API trata a nova sequência sem exigir reinício do servidor |

**Teste automatizado (API, sem Wokwi):** na raiz do repositório, execute:

```powershell
python -m pip install -r marco3/api/requirements-test.txt
python -m unittest discover -s marco3/testes -v
```

Os testes cobrem login/logout, proteção de formulários, autenticação do dispositivo, vínculo do paciente, contrato JSON, deduplicação, sequência, reinício e heartbeat. O sketch foi compilado com os headers do core ESP32 (Arduino) 2.0.17. **A integração Wokwi → túnel → API deve ser ensaiada pelos integrantes antes da apresentação**, pois depende do simulador e da rede.

## 7. Decisões de projeto

- **Por que HTTP no Marco 3?** Permite exercitar requisições e respostas REST, códigos de status e autenticação na mesma fronteira produtor/consumidor.
- **Por que o ESP32 não faz login?** Ele é uma máquina e se autentica com uma chave de dispositivo, não com a senha de um cuidador.
- **Quem define qual cuidador recebe os dados?** A API. Um vínculo configurado no servidor restringe a consulta, independentemente do `entityId` enviado pelo navegador.
- **Por que não há banco de dados?** Com um único paciente e um único cuidador, guardar o último evento em memória é suficiente para demonstrar comunicação, autenticação e autorização com menos partes.
- **O que acontece se a rede cair?** A decisão e os atuadores permanecem no ESP32; a fila tenta entregar os eventos quando a conexão se restabelece.
- **Por que HTTPS até o túnel?** HTTP não criptografa. O ESP32 valida o certificado do túnel com raízes conhecidas: a chave autentica o dispositivo e o TLS protege o canal.
- **Por que um túnel?** O Wokwi gratuito só alcança a internet. O túnel dá à API do nosso PC um endereço HTTPS público, sem custo e sem conta, mantendo tudo rodando no terminal como no Marco 2.

## 8. Limitações assumidas conscientemente

- A roupa inteligente e o sensor de FC são simulados; BLE e smartphone-gateway da modelagem conceitual das atividades iniciais **não foram implementados** nesta versão.
- Apenas **um paciente, um cuidador e um ESP32** estão cadastrados. Os vínculos são definidos no servidor, não editáveis no painel.
- Estado, eventos recentes e métricas são guardados **em RAM**: reiniciar a API apaga o histórico; não há PostgreSQL/Neon.
- A fila do ESP32 tem capacidade para **12 transições** e descarta a mais antiga ao encher.
- Um HTTP POST é síncrono e pode atrasar brevemente uma amostragem; não há garantia de tempo real rígido.
- A disponibilidade é inferida após **120 segundos reais** sem heartbeat/evento, não é uma confirmação clínica de funcionamento.
- A ligação Wokwi → PC depende do túnel gratuito da Cloudflare, que não tem garantia de disponibilidade e troca de URL a cada reinício. O HTTPS protege o trecho ESP32 → Cloudflare; do túnel até a API o tráfego é local, dentro do PC.
- A atuação usa **um LED e um buzzer**; os estados são distinguidos por apagado, aceso e piscando.
- Não há recuperação persistente de sessões, limite de tentativas no login, múltiplos perfis ou gestão de usuários. Não usar como produto real de segurança ou saúde.

---

**Registro das entregas anteriores:** [`../atividade-01.md`](../atividade-01.md), [`../atividade-02.md`](../atividade-02.md) e [`../marco2/README.md`](../marco2/README.md). Esses arquivos permanecem preservados para mostrar a evolução do trabalho.
