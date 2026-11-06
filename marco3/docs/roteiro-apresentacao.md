# Roteiro de apresentação — Marco 3 (10 minutos)

**Objetivo:** demonstrar arquitetura, dois ciclos produtor-consumidor, quatro melhorias solicitadas (WebSocket, fila, TimescaleDB e simulação) e os conceitos de computação ubíqua estudados na disciplina. Os valores são sintéticos.

| Tempo | Tela ou operação | Explicação objetiva |
|---|---|---|
| 0:00–1:00 | [Arquitetura](visuais/arquitetura-final.svg) | ESP32/Wokwi, API, fila, regra, banco e painel; dois ciclos de comunicação |
| 1:00–2:00 | Circuito virtual + Serial Monitor | Potenciômetro/MPU6050, lote de três leituras, HTTP assinado com HMAC |
| 2:00–3:00 | Painel autenticado | WebSocket mantém conexão e envia evento sem atualizar a página; REST somente como contingência |
| 3:00–4:00 | Indicadores da fila | Lotes enfileirados/processados/pendentes; consumidor FIFO; fila em memória de até 128 lotes |
| 4:00–5:20 | Gráfico e SQL Editor | FC × tempo, três hypertables, `time_bucket`, distinção entre estado volátil e histórico durável |
| 5:20–6:40 | Cenários `1`, `2` e `4` | Normalidade e atenção por FC elevada **em repouso**, com janela, cobertura e histerese |
| 6:40–7:40 | Botão Reconhecer alerta | Cuidador produz comando, ESP32 consome, silencia buzzer e retorna ACK |
| 7:40–8:40 | Cenários `3` e `f` | Ausência de sensor, queda de comunicação, `DADOS_INSUFICIENTES` e modo local |
| 8:40–9:30 | SQL de histórico após reiniciar API | Leituras continuam no TimescaleDB, estados operacionais em memória reiniciam |
| 9:30–10:00 | Conclusão | Benefícios e limites: fila volátil, HMAC ≠ TLS, protótipo com sensores sintéticos |

## Script conceitual (frases que cada integrante deve saber explicar)

**1. Por que o sistema é ubíquo?** O dispositivo integra sensoriamento e atuação, comunica-se com um serviço externo e entrega informações contextualizadas ao usuário.

**2. Por que uma fila?** A rota valida e enfileira; um consumidor único retira os lotes na ordem de chegada e executa a regra. Não é broker persistente nem garantia de entrega de ponta a ponta.

**3. Por que WebSocket?** Para o servidor notificar o painel quando há uma mudança, em vez de depender exclusivamente de requisições periódicas do navegador.

**4. Por que TimescaleDB?** Para armazenar séries temporais e facilitar consultas, agrupamento por `time_bucket` e comparação de períodos. Três hypertables guardam amostras, transições e comandos.

**5. O que torna a simulação melhor?** Os cenários são reproduzíveis: FC normal, FC alta com repouso, FC alta com movimento, sensor ausente, queda da rede e recuperação. Permitem explicar as decisões da regra.

**6. Como a segurança funciona?** ESP32 usa `deviceId` e HMAC-SHA256 sobre timestamp, método, rota e corpo. A API confere assinatura e vínculo com o paciente; o cuidador autentica-se por sessão. HMAC não cifra HTTP e a janela temporal não impede todo replay dentro dos 120 segundos.

**7. Quais são as limitações conscientes?** Um único worker da API, fila/estado/comando em memória, sem reenvio durável durante falha do banco, sensores virtuais e HMAC sem criptografia de transporte.

## Ordem de abertura para uma demonstração repetível

Na **raiz do repositório**: iniciar a API (`app.py`), abrir `/login`, iniciar o túnel Cloudflare, atualizar `API_BASE_URL` no `config.h` privado do Wokwi, iniciar o ESP32 e abrir o SQL Editor com as consultas prontas. O procedimento íntegro está em [GUIA_EXECUCAO_E_TESTES.md](GUIA_EXECUCAO_E_TESTES.md).
