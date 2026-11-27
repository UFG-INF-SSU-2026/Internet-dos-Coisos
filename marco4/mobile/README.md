# App Android do cuidador (Marco 4)

Kotlin + Jetpack Compose. Sem bibliotecas de rede extras (`HttpURLConnection` + `org.json`).
O contrato com a API está em [`../contrato/app-v1.json`](../contrato/app-v1.json).

| Arquivo | Papel |
|---|---|
| `Api.kt` | Login → token Bearer; estado; reconhecer alerta; envio do movimento. Só aceita `https://`. |
| `Movimento.kt` | Acelerômetro: pico de \|aceleração/9,81 − 1\| (em g) entre dois envios. |
| `MainActivity.kt` | ViewModel (consulta a cada 2 s, envio do movimento a cada 2 s) e as telas de login e de estado. |

## Segurança

- Nenhuma chave no APK. O usuário e a senha do cuidador geram um token assinado pela API, que expira em 8 h e fica só em memória.
- `usesCleartextTraffic="false"`: o app não fala HTTP. A URL do túnel Cloudflare é `https://` e o Android valida o certificado com as CAs do sistema.
- Resposta 401 (token expirado ou inválido) volta para a tela de login.

## Como compilar e gerar o APK

1. Android Studio (Ladybug ou mais novo) → **Open** → pasta `marco4/mobile`.
   O repositório não traz o Gradle wrapper; se o Studio pedir, aceite criá-lo (ou rode `gradle wrapper` com Gradle 8.9+).
2. Espere o *Gradle sync*. Se o Studio sugerir atualizar o AGP, o Kotlin ou o Compose BOM, pode aceitar.
3. **Build → Build App Bundle(s) / APK(s) → Build APK(s)**.
4. Copie `app/build/outputs/apk/debug/app-debug.apk` para `marco4/apk/coisos-cuidador.apk` e faça commit.

## Como usar na demonstração

1. Suba banco → API → túnel (`cloudflared tunnel --url http://127.0.0.1:5000`) → Wokwi.
2. No app, cole a URL `https://….trycloudflare.com`, entre com `cuidador01` e a senha do `.env`.
3. Cenário de FC alta no Wokwi: o estado vai para **ATENCAO** e o botão **Reconhecer alerta** fica ativo.
4. Balance o celular: o movimento passa a vir do celular (`fonte: celular`) e o alerta de FC alta é suprimido ou encerrado (`razao = movimento_no_celular`).

## Limitações conhecidas

- O app faz polling a cada 2 s (não usa o WebSocket do painel).
- O acelerômetro continua ligado enquanto o app está aberto, inclusive em segundo plano. Em produção, isso iria para um serviço em primeiro plano.
- Não há testes instrumentados; os comportamentos de API do app estão cobertos em `marco4/testes/test_app_mobile.py`.
