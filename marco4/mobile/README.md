# App Android do cuidador (Marco 4)

Kotlin + Jetpack Compose. O app continua sendo o segundo produtor do sistema: o acelerômetro do celular envia o contexto de movimento para a mesma fila FIFO usada pelo ESP32.
O contrato com a API está em [\`../contrato/app-v1.json\`](../contrato/app-v1.json).

## Painel Android

A tela nativa consome a mesma fonte de verdade usada pelo painel web, \`GET /api/pacientes/{id}/estado\`, com polling REST a cada 2 segundos (decisão D25). O painel web usa WebSocket; o Android reflete a atualização no próximo ciclo de consulta.

O painel do app exibe:
- Estado e contato recente do ESP32.
- FC média, movimento e origem do contexto (ESP32/celular).
- Cobertura das janelas de frequência cardíaca e movimento.
- Lotes recebidos e indicadores da fila FIFO (pendentes, enfileirados, processados e capacidade).
- Gráfico recente de frequência cardíaca, com linha de referência tracejada em 100 bpm.
- Ciclo do comando do cuidador (\`PENDENTE → ENTREGUE → EXECUTADO\`), com botão desabilitado enquanto existir comando não executado.
- Últimas transições de estado e últimos lotes processados.
- Estado do TimescaleDB, erros/gravações não persistidas e indicadores do segundo produtor Android.
- Consulta manual ao endpoint de histórico temporal.

## Arquivos

| Arquivo | Papel |
|---|---|
| \`Api.kt\` | Login Bearer, estado, histórico, reconhecer alerta e envio de movimento; somente HTTPS |
| \`Logica.kt\` | Intensidade do acelerômetro e conversão/testabilidade da resposta da API |
| \`Movimento.kt\` | Acelerômetro: pico de \`|aceleração/9,81 − 1|\` (em g) entre envios |
| \`MainActivity.kt\` | ViewModel, polling, envio do segundo produtor e painel Compose |
| \`LogicaTest.kt\` | Testes JVM de sensor, URL, payload, estado, fila, comando e histórico |

## Segurança

- Nenhuma chave fica no APK. Usuário e senha geram token assinado pela API, válido por 8 h e mantido em memória.
- \`usesCleartextTraffic="false"\`: só HTTPS. O Android valida o certificado com as CAs do sistema.
- Resposta 401 (token expirado/inválido) retorna à tela de login.
- A autorização de acesso ao paciente continua centralizada na API.

## Como compilar e gerar o APK

Versões: Gradle 9.9.3 (wrapper), AGP 9.5.3, plugin Compose 2.4.21, Compose BOM 2026.09.00, \`compileSdk\`/\`targetSdk\` 37 e \`minSdk\` 26.

1. Android Studio → **Open** → pasta \`marco4/mobile\` e aguarde o Gradle Sync.
2. Execute os testes: \`./gradlew testDebugUnitTest\`.
3. Gere o APK: \`./gradlew assembleDebug\`.
4. O APK fica em \`app/build/outputs/apk/debug/app-debug.apk\`.

## Demonstração

1. Suba banco → API → túnel Cloudflare → Wokwi.
2. Entre no app com a URL HTTPS, o usuário \`cuidador01\` e a senha local do cuidador.
3. Gere FC alta em repouso no Wokwi e observe o estado \`ATENCAO\`.
4. Reconheça o alerta: o ESP32 deve silenciar o buzzer e devolver ACK; o status do comando aparece no próximo polling.
5. Balance o celular: o segundo produtor informa movimento e o contexto pode suprimir o alerta de FC alta.
6. Consulte o histórico temporal para verificar as leituras disponíveis no banco.

## Limitações conhecidas

- O app faz polling a cada 2 s, não WebSocket. A atualização pode ocorrer até um ciclo depois do painel web.
- O acelerômetro permanece ativo enquanto o app está aberto; em produção, avaliar serviço em primeiro plano.
- O histórico persistido é consultado manualmente; o painel de estado atualiza no polling.
- Testes JVM não substituem testes instrumentados nem ensaio em celular físico.
