# Protocolo de execução e verificação — Marco 3

Este roteiro padroniza como reproduzir as funcionalidades do Marco 3. Os comandos completos estão em [GUIA_EXECUCAO_E_TESTES.md](GUIA_EXECUCAO_E_TESTES.md). Use dados sintéticos; credenciais ficam somente no `.env` e `config.h` privados.

## 1. Preparação e segurança

1. Abrir o repositório no VS Code, na raiz do projeto.
2. Criar `.venv` e instalar `requirements-test.txt` e `requirements-temporal.txt`, que incorporam a biblioteca WebSocket.
3. Gerar as credenciais com `marco3/api/gerar_config.py` e registrar a senha do cuidador de modo privado.
4. Configurar `DATABASE_URL` em `marco3/api/.env`, sem registrar a URL em arquivos versionados.
5. Confirmar com `git check-ignore` que `.env` e `config.h` estão excluídos do Git.

## 2. Banco temporal

1. `python marco3/scripts/verificar_banco.py` verifica extensão e hypertables.
2. No editor SQL, consultar `timescaledb_information.hypertables`; devem existir `leituras`, `eventos_estado` e `comandos`.
3. Após enviar lotes, consultar contagem e série `ORDER BY ts DESC`.
4. Reiniciar a API e consultar novamente para demonstrar histórico persistente.

## 3. API, interface e WebSocket

1. Executar `marco3/api/app.py` e abrir `/login` com `cuidador01`.
2. Observar no rodapé `WebSocket conectado`; atualizar a página não deve ser necessário para receber eventos.
3. Acompanhar FC × tempo, estado, cobertura de amostras, métricas da fila e últimos lotes em ordem FIFO.
4. Usar o botão **Consultar histórico no banco**, que consulta a API autenticada e desenha os pontos em ordem cronológica.

## 4. Wokwi e ciclos

1. Abrir cópia **privada** do Wokwi com `sketch.ino`, `diagram.json`, `libraries.txt`, `config.h` local.
2. Atualizar `API_BASE_URL` com o endereço do túnel temporário; não acrescentar rota à URL-base.
3. Observar `HTTP 200` no Serial Monitor para os lotes.
4. Executar os cenários `1`, `2`, `3`, `4`, `a`, `f` e observar efeitos no painel e nos estados.
5. Em `ATENCAO`, clicar em **Reconhecer alerta**, observar silenciamento do buzzer e ACK no Serial Monitor.
6. Consultar `comandos` no TimescaleDB para observar `PENDENTE`, `ENTREGUE` e `EXECUTADO`.

## 5. Verificações de código

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s marco3\testes -v
```

Os testes automatizados complementam a execução do cenário, mas não substituem a demonstração de WebSocket, Wokwi e persistência temporal.

## 6. Referências para explicar

- [Arquitetura, sequência e gráficos](DIAGRAMAS_E_GRAFICOS.md)
- [Regra de contexto](../api/regra.py)
- [Esquema SQL](../api/sql/timescaledb.sql)
- [Roteiro de 10 minutos](roteiro-apresentacao.md)
