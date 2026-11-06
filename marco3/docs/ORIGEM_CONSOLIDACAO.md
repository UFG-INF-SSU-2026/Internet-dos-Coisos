# Proveniência técnica do Marco 3 consolidado

A versão final utiliza a `main` do repositório `UFG-INF-SSU-2026/Internet-dos-Coisos` como referência e reúne contribuições das branches `marco3-enxuto` (versão apresentada pelo grupo) e `timescaledb` (módulo temporal), além das melhorias solicitadas pelo professor.

| Origem | Componentes preservados ou integrados |
|---|---|
| `main` | Rotas HTTP/HMAC, autenticação e autorização, cálculo de estado em `regra.py`, dois ciclos do dispositivo/cuidador, sketch com buzzer por `tone()` |
| `marco3-enxuto` | Geração privada da chave e do `.env`/`config.h`, com sincronização da chave do ESP32 e da API |
| `timescaledb` | `armazenamento.py`: gravação temporal de leituras, transições de estado e status de comandos; ampliado com consultas e diagnósticos de conexão |
| Consolidação | Fila FIFO, consumidor, WebSocket no painel, consulta e gráfico temporal, simulação de cenários, scripts e documentação padronizada |

`temporal.py` é um **adaptador**, não um segundo banco. As três hypertables mantêm uma responsabilidade única por tipo de evento. O sketch preserva o modelo HTTP assinado já apresentado; não substituímos desnecessariamente a comunicação do ESP32.

A consolidação é **de conteúdo**: as branches de origem permanecem disponíveis com seus históricos. A versão publicada como entrega do grupo utiliza o código consolidado, sem fazer alterações nas branches históricas.

## Pontos técnicos documentados

- `asyncio.Queue` é uma fila em memória; opera com um único processo Uvicorn.
- O histórico das leituras persiste no TimescaleDB, enquanto estados e comandos pendentes são voláteis.
- A chave HMAC é gerada localmente e não deve ficar em commits nem em simulação Wokwi pública.
- HTTP com HMAC não equivale a TLS; o projeto é um protótipo acadêmico com dados sintéticos.
