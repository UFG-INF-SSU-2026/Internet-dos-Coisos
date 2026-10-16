# Marco 3 — Roteiro da apresentação (10 min)

## Antes de começar (montar 10 min antes)

1. Terminal 1, em `marco3/api`: `python app.py`
2. Terminal 2: `cloudflared tunnel --url http://127.0.0.1:5000` → copiar a URL `https://...trycloudflare.com` (no `config.h` use `http://`)
3. Wokwi: colar a URL em `config.h` e iniciar a simulação. Conferir no serial: `lote N: HTTP 200`.
4. Navegador: `http://127.0.0.1:5000/login` aberto **sem** login (para a demo de autorização).
5. Abrir no editor: `regra.py`, `app.py` (funções `dispositivo_autenticado` e `dispositivo_autorizado`), `sketch.ino` (`assinar` e `requisicao`).
6. Potenciômetro baixo (FC ~80), MPU6050 parado (repouso).

## Roteiro

| Tempo | Quem | O que falar | O que mostrar |
|---|---|---|---|
| 0:00–1:30 | ______ | **Arquitetura e evolução.** Marco 2: ESP32 decidia tudo e publicava por MQTT. Marco 3: ESP32 mede e atua; a API em Python analisa e decide; dois ciclos produtor-consumidor. Decisões D1, D5, D8. | `docs/arquitetura.mmd` |
| 1:30–3:00 | ______ | **Canal seguro e autenticação do dispositivo.** Cada mensagem vai assinada com HMAC-SHA256 (chave + horário); a chave não trafega. Por que não HTTPS: o Wokwi não completa TLS (D17), mostramos o teste. | `assinar` no sketch; `dispositivo_autenticado` no app; `test_corpo_alterado_invalida_assinatura`. *(Opcional: chave errada no `config.h` → serial mostra `HTTP 401`.)* |
| 3:00–4:30 | ______ | **Login e autorização do cuidador.** Senha com hash scrypt; cookie de sessão; vínculo cuidador ↔ paciente. | `/painel` sem login → vai para `/login`; senha errada → erro; login certo → painel. `http://127.0.0.1:5000/api/pacientes/patient-9999/estado` → `403`. |
| 4:30–6:30 | ______ | **Ciclo 1 ao vivo.** Lote a cada 3 s; a API aplica a regra (últimas 10 leituras, cobertura 70%, 100/92 bpm, 2 avaliações) e devolve o estado. | Subir o potenciômetro (>100 bpm). Em ~10 s: painel `ATENCAO`, LED aceso, buzzer. Mostrar `avaliar()` em `regra.py`. |
| 6:30–8:00 | ______ | **Ciclo 2 ao vivo.** O cuidador vira produtor; o ESP32 vira consumidor e produz o ack. | Clicar "Reconhecer alerta" → `PENDENTE` → `ENTREGUE` → buzzer para (LED continua) → `EXECUTADO`. Serial: `comando ...: ack HTTP 200`. |
| 8:00–9:30 | ______ | **Falha de rede.** Sem fila (D12); o ESP32 entra em modo local (D7). | Botão vermelho (ou tecla `f`). Serial: `MODO LOCAL` após 8 s; painel vai a `DADOS_INSUFICIENTES` / "sem contato recente". Clicar de novo → volta ao normal. |
| 9:30–10:00 | todos | **Limitações** e perguntas. | `docs/decisoes.md` |

## Sequência da demo ao vivo (≈ 5 min, tudo já rodando)

Cada mudança de estado leva **~10 s** para aparecer: fale enquanto espera.

| Min | Ação na bancada | O que aparece | O que falar enquanto espera |
|---|---|---|---|
| 0:00 | Painel aberto em `NORMAL`; serial com `lote N: HTTP 200` | — | "A cada 3 s o ESP32 manda 3 leituras assinadas com a chave." |
| 0:30 | Abrir `/api/pacientes/patient-9999/estado` em outra aba | `403` | autorização do cuidador |
| 1:00 | Potenciômetro para ~130 bpm | ~10 s: `ATENCAO`, LED aceso, buzzer | regra em `regra.py`: média, 100/92, 2 avaliações |
| 1:45 | Clicar **Reconhecer alerta** | `PENDENTE` → `ENTREGUE` → `EXECUTADO` em ~3–6 s; buzzer para, LED continua | ciclo 2: quem produz e quem consome; por que o LED continua |
| 2:45 | Potenciômetro para ~70 bpm | ~10 s: `NORMAL`, LED apaga | histerese |
| 3:15 | Botão vermelho (ou `f`) | serial `MODO LOCAL` em 8 s; painel `DADOS_INSUFICIENTES` / "sem contato recente" | sem fila (D12), modo local (D7) |
| 3:45 | Potenciômetro para ~130 com a rede "caída" | LED + buzzer pelo ESP32 sozinho | "sem rede, o paciente ainda é alertado" |
| 4:15 | Botão vermelho de novo; potenciômetro para ~70 | serial `API respondeu`; painel volta a `NORMAL` | — |
| 4:45 | Encerrar | — | limitações |

## Perguntas prováveis (todos devem saber responder)

1. **Autenticação × autorização?** Autenticação = quem é você (chave / senha). Autorização = você pode fazer isso (vínculos). No código: `dispositivo_autenticado` × `dispositivo_autorizado`.
2. **Por que o ESP32 usa chave e não senha?** É uma máquina; não digita senha nem mantém sessão de navegador.
3. **Onde fica a chave?** `api/.env` e `produtor/config.h`, gerados por `gerar_config.py`, fora do GitHub (`.gitignore`).
4. **Quem captura o tráfego vê a chave?** Não: só a assinatura trafega, e dela não se tira a chave. As leituras, sim, podem ser lidas (sem HTTPS no Wokwi).
5. **Por que não HTTPS?** Testamos: no Wokwi nenhum HTTPS completa (nem com o Google, nem sem validar certificado), e HTTP simples funciona. Em hardware real, voltaríamos ao HTTPS mantendo a assinatura (D17).
5b. **E se alguém capturar e reenviar uma mensagem?** O horário vai dentro da assinatura: depois de 120 s a API recusa; dentro disso, lote repetido é ignorado pelo `loteId`.
6. **Do túnel até a API é criptografado?** Não, mas é dentro do próprio PC. Limitação assumida.
7. **Quem produz e quem consome em cada ciclo?** Ver tabela em `decisoes.md`.
8. **Por que a análise saiu do ESP32? O que se perdeu?** Menos C, regra testável em Python. Perdeu-se a decisão completa offline, compensada pelo modo local (D5, D7, D12).
9. **Por que o ESP32 pergunta pelo comando em vez de receber?** Ele não tem endereço público; HTTP é pedido/resposta. 3 s foi escolha nossa.
10. **E se o ack se perder?** O comando fica `ENTREGUE`, o ESP32 recebe de novo e silencia de novo (sem efeito extra).
11. **Por que reconhecer não apaga o LED?** O cuidador ter visto não significa que o risco passou (D14).
12. **O que é cobertura? E histerese?** Cobertura = % de leituras válidas entre as últimas 10 (mín. 70%). Histerese = entra acima de 100, só sai abaixo de 92, para não ficar alternando.
13. **Por que a senha é guardada como hash com salt?** Se o `.env` vazar, a senha não aparece; o salt impede comparar com tabelas prontas.
14. **E se a API reiniciar?** Os dados estão em memória e se perdem (D13).
15. **O que é o `loteId`?** `bootId-sequência`. Se o mesmo lote chegar duas vezes, a API ignora; o `bootId` evita colisão depois de reiniciar o ESP32.
