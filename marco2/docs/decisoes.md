# Decisões de planejamento — Marco 2

## 1. Componentes envolvidos

**Produtor:** protótipo individual de Matheus Augusto (Marco 1), responsabilidade
de estado e processamento temporal. Já emitia evento JSON com identidade,
sequência e razão da decisão; foi estendido para publicar por MQTT.

**Consumidor:** serviço em Python que assina o tópico, valida o contrato e
produz efeito observável (painel de estado e alerta ao cuidador).

## 2. Fluxo de comunicação

```
ESP32 (borda) --publish--> broker MQTT --deliver--> serviço consumidor
```

O produtor não conhece o consumidor. Essa escolha vem da Atividade 02: no
projeto, a telemetria vai para mais de um destino (serviço de processamento,
aplicativo do cuidador, painel de acompanhamento).

## 3. Mecanismo escolhido: MQTT

| Critério | Por que MQTT |
|---|---|
| Múltiplos consumidores | publicação e assinatura desacoplam produtor e destino |
| Desacoplamento espacial | o produtor publica em tópico, não em endereço |
| Dispositivo restrito | protocolo leve, adequado ao ESP32 |
| Silêncio observável | *last will* anuncia desconexão sem encerramento |

HTTP foi considerado e não adotado nesta fronteira: exigiria que o dispositivo
conhecesse o endereço do serviço e tratasse retry e disponibilidade por conta
própria. HTTP continua adequado para consulta e comando explícito, que não são
o caso deste fluxo.

**QoS.** O produtor publica em QoS 0 e o consumidor assina em QoS 1. QoS 1 no
produtor traria retransmissão pelo broker, mas o evento é de transição de
estado — raro, com `sequence` e fila local própria — e uma eventual duplicata
já é reconhecida pelo `eventId`. O que importa aqui não é a garantia de
transporte, e sim que o consumidor saiba dizer o que recebeu repetido ou
deixou de receber.

## 4. Contrato

Ver `contrato/README.md`. Versão 1, campo `schemaVersion` explícito. O consumidor
rejeita versão não suportada em vez de interpretar parcialmente.

## 5. Condição de falha tratada

**Broker indisponível.** O produtor mantém fila local: continua amostrando,
avaliando a janela e transitando de estado, e guarda os eventos que não
conseguiu publicar. Na reconexão, reenvia em ordem.

O consumidor usa `sequence` para reconhecer duplicata, salto e chegada fora de
ordem — o transporte não informa nada disso.

Decisão registrada: a desconexão interrompe a **entrega**, não a **decisão**.
O alerta local (LED e buzzer) continua funcionando sem rede, coerente com a
política de degradação da Atividade 02.

## 6. Responsabilidades

| Parte | Responsável |
|---|---|
| Produtor, publicação MQTT e fila local | Matheus Augusto Ferreira Medeiros |
| Consumidor e validação do contrato | Felipe Alves Leão de Araújo |
| Repositório, README e execução na demonstração | Felipe O Carvalho |
| Diagrama, decisões arquiteturais e comparação | Murilo Bernardo |

Todos os integrantes executam a integração antes da demonstração e conseguem
explicar o fluxo completo, o mecanismo escolhido e o comportamento diante da
falha.

## 7. O que não foi integrado

BLE, aplicativo Android, nuvem, histórico de longo prazo e watermark de eventos
tardios. O objetivo do Marco 2 é validar **uma** fronteira real, não o sistema
completo.
