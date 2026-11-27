# Plano do Marco 4 (entrega em 27/11/2026)

Marque `[x]` conforme cada item for concluído e cite o commit ou PR quando houver.
O artigo está entre os 5 itens obrigatórios **desta** entrega, não só da final.

## 0. Feedback do Marco 3: registro de atendimento

Os quatro apontamentos já foram implementados no commit `f59a370` (06/11). Falta só registrar o atendimento no README do Marco 4.

| Apontamento | Alteração | Evidência | Situação |
|---|---|---|---|
| WebSocket | `WS /ws/pacientes/{id}` autenticado, em `app.py` e `painel.html` | `test_websocket_precisa_sessao`, `test_websocket_envia_estado_ao_receber_leituras` | Atendido |
| Banco temporal | TimescaleDB com 3 hypertables (`armazenamento.py`, `sql/timescaledb.sql`) | `test_consolidacao.TestarPersistenciaIntegrada`, mais consulta SQL depois de reiniciar a API (mostrar no vídeo) | Atendido |
| Melhorar a simulação | Cenários `0–4`, `a` e `f` no `sketch.ino`, com modo local em caso de falha | Serial Monitor e painel (vídeo) | Atendido |
| Transformar em fila | `asyncio.Queue` com um único consumidor, deduplicação e erro 503 quando enche | `test_fila_evidencia_ordem_e_contadores`, `test_fila_processa_e_preserva_estado` | Atendido |

- [x] Colar a tabela acima no `marco4/README.md` (`6cc87df`)

## Trilha A: app Android (a mais crítica)

Código em `marco4/mobile` (Kotlin + Compose). O passo a passo para compilar está em `marco4/mobile/README.md`.

- [x] Esqueleto do projeto Android Studio em `marco4/mobile` (`1f11384`)
- [x] Tela de login: o usuário e a senha do cuidador geram um token, e nenhuma chave fica no APK
- [x] Tela de estado com polling de 2 s: carregando, erro de rede e resultado
- [x] Botão **Reconhecer alerta**
- [x] Acelerômetro envia a intensidade do movimento a cada 2 s (é o segundo produtor)
- [x] Só HTTPS (`usesCleartextTraffic=false`), e o Android valida o certificado do túnel
- [ ] Abrir no Android Studio, sincronizar o Gradle e corrigir o que não compilar
- [ ] Testar num celular real contra a URL do túnel Cloudflare
- [ ] Gerar o APK e salvar em `marco4/apk/coisos-cuidador.apk`
- [ ] Tirar prints das telas (login, estado NORMAL, ATENCAO, erro de rede) para o README e o artigo

## Trilha B: API, testes e CI ✅ (PR #3, merge `6f1a443`)

- [x] Copiar `marco3/` para `marco4/`, sem `.env` nem `config.h` (`78e04df`)
- [x] `POST /api/app/login`, que devolve o token Bearer (8 h) (`dddf3d3`)
- [x] `POST /api/app/leituras`: movimento com `capturadoEmMs`; leitura atrasada, adiantada ou fora de ordem recebe 422
- [x] Token aceito nas rotas de estado, histórico e comando
- [x] Leituras do celular na mesma fila FIFO do ESP32
- [x] Mudança de contexto: movimento do celular suprime o alerta de FC alta (`razao = movimento_no_celular`)
- [x] Contrato `marco4/contrato/app-v1.json`
- [x] Teste: token inválido, forjado ou expirado devolve 401 (`0b62167`)
- [x] Teste: acesso a outro paciente devolve 403
- [x] Teste: leitura do celular atrasada é rejeitada
- [x] Teste: movimento do celular suprime o alerta
- [x] CI com caminhos `marco4/`, todos os módulos (inclusive `TestarCredenciaisPrivadas`) e relatório JUnit como artefato (`b6aadae`)
- [x] CI verde em Python 3.10 e 3.12 (42 testes)

## Trilha C: documentação e evidências (`395c8e1`, `386e895`, `6cc87df`)

- [x] `marco4/README.md` reescrito para o Marco 4, apontando para cada entrega
  - [x] As três tabelas no estilo do swifties (itens obrigatórios, requisitos mantidos, verificações → evidência)
  - [x] A tabela de feedback (seção 0)
  - [x] Link do relatório JUnit do CI
  - [x] README da raiz aponta para o Marco 4
  - [ ] Atualizar a situação dos itens 1 (APK) e 5 (artigo) quando ficarem prontos
- [x] `marco4/docs/implantacao.md`
  - [x] Versões (Python, FastAPI, TimescaleDB, cloudflared, Android)
  - [x] Ordem de execução: banco → API → túnel → Wokwi → app
  - [x] Credenciais de teste: como gerar com `gerar_config.py`, sem publicar a senha
  - [x] Configuração do banco (`DATABASE_URL`, `sql/timescaledb.sql`)
- [x] `marco4/docs/verificacao.md` com as 4 verificações do PDF, no formato do pequi
  - [x] Evidência da suíte em `docs/evidencias/testes-api.txt`
  - [ ] Preencher a coluna **Registro** do ensaio completo (seção 2) durante o ensaio
- [x] Limitações declaradas (segurança, conectividade, desempenho, energia, simulação, dados pessoais)
  - [x] O ESP32 continua em HTTP com HMAC, porque o Wokwi não completa HTTPS (decisão D17)
  - [x] A chave versionada em 16/10 já foi trocada (conferido: a chave do `.env` atual é diferente)
  - [x] O app faz polling, não WebSocket
  - [x] O celular do cuidador faz o papel do sensor de movimento do paciente na demonstração
- [x] Declaração de uso de IA (Marco 4)
  - [ ] O grupo completa a linha das ferramentas usadas nos marcos anteriores
- [ ] Contribuições individuais dos 4 integrantes (a tabela existe no `marco4/README.md`; cada um preenche a sua)
- [x] Atualizar `docs/decisoes.md` com as decisões do Marco 4 (D23 a D31)
- [x] Diagrama atualizado com o app (`docs/arquitetura.mmd`, renderizado no README)
  - [ ] Regenerar `docs/visuais/arquitetura-final.svg` a partir do `.dot` (precisa do Graphviz: `dot -Tsvg arquitetura-final.dot -o arquitetura-final.svg`)

## Trilha D: artigo de 10 a 15 páginas

- [ ] Estrutura e template definidos
- [ ] Introdução e fundamentação (a partir de `decisoes.md` e do README do Marco 3)
- [ ] Arquitetura (a partir de `DIAGRAMAS_E_GRAFICOS.md`), com os dois produtores e a fila
- [ ] Implementação: ESP32, API, banco temporal, app
- [ ] Segurança: HMAC no dispositivo, sessão e token, autorização por paciente
- [ ] Avaliação: resultados dos testes e do CI (no fim da tarde)
- [ ] Limitações e trabalhos futuros (ver pendências abaixo)
- [ ] Revisão final e PDF em `marco4/docs/`

## Fim do dia: todos juntos

- [ ] Ensaio do fluxo completo: banco → API → túnel → Wokwi → app → alerta → balançar o celular → reconhecer alerta
- [ ] Vídeo de até 15 min com os 4 integrantes
- [ ] Link do vídeo no README
- [ ] Tag `marco4` no commit entregue (`git tag marco4 && git push origin marco4`)
- [ ] Entrega

## Pendências declaradas para 11/12

Vão para o README com impacto e justificativa, como o PDF permite.

- [ ] TLS no ESP32
- [ ] Teste de integração com TimescaleDB real no CI
- [ ] Testes instrumentados do app
- [ ] Recuperar o estado e o comando pendente quando a API reinicia
