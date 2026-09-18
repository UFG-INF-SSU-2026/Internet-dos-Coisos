# Contrato do evento — versão 1

Publicado pelo produtor em `.../state`, consumido pelo serviço.

| Campo | Tipo | Significado |
|---|---|---|
| `schemaVersion` | int | versão do contrato; o consumidor rejeita versões que não entende |
| `eventType` | string | o que aconteceu (`vitals.state.changed`) |
| `eventId` | string | identificador único do evento; base da deduplicação |
| `deviceId` | string | quem produziu |
| `entityId` | string | entidade observada (pseudonimizada) |
| `eventTimeMs` | int | tempo desde o boot do dispositivo — **não é UTC** |
| `sequence` | int | ordem de produção; revela salto, repetição e inversão |
| `value` | float ou null | FC média da janela; `null` quando não há amostra válida |
| `unit` | string | unidade de `value` |
| `state` | string | `DESCONHECIDO`, `DADOS_INSUFICIENTES`, `NORMAL` ou `ATENCAO` |
| `motion` | string | movimento predominante da janela |
| `coverageFc` / `coverageMov` | float | fração da janela preenchida por leituras válidas |
| `reason` | string | razão da transição |

## Obrigatórios e opcionais

O consumidor exige `schemaVersion`, `eventType`, `eventId`, `deviceId`,
`entityId`, `sequence` e `state`: sem eles não há como identificar, ordenar
nem interpretar o evento. Os demais (`value`, `unit`, `motion`, `coverage*`,
`reason`) enriquecem o painel, mas a ausência de um deles não invalida o
evento. Isso permite que um produtor futuro omita uma medida sem obrigar
uma nova versão do contrato.

## Tópicos

| Tópico | Conteúdo |
|---|---|
| `.../state` | eventos de mudança de estado |
| `.../status` | `online` publicado na conexão; `offline` publicado pelo broker via *last will* |

## Versionamento

Mudança compatível (campo novo opcional) mantém `schemaVersion`. Mudança
incompatível (campo removido, renomeado ou com significado alterado)
incrementa a versão. O consumidor rejeita explicitamente versão que não
suporta, em vez de interpretar campos pela metade.

## Limitação declarada

`eventTimeMs` é `millis()`: tempo desde o início da execução, não data e hora
absolutas. Uma integração com histórico de longo prazo exigirá sincronização
de relógio ou conversão no consumidor.
