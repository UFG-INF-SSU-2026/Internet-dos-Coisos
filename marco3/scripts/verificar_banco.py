"""Verifica acesso a TimescaleDB, hypertables e contagem sem exibir a senha.

Na raiz: .\\.venv\\Scripts\\python.exe marco3\\scripts\\verificar_banco.py
Requer DATABASE_URL em marco3/api/.env e psycopg[binary] instalado.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from app import carregar_env_local  # noqa: E402


def main():
    carregar_env_local()
    import os
    url = os.getenv('DATABASE_URL', '')
    if not url:
        print('[ERRO] DATABASE_URL ausente de marco3/api/.env.')
        return 1
    try:
        from armazenamento import Armazenamento
    except ImportError:
        print('[ERRO] Instale a biblioteca: pip install "psycopg[binary]"')
        return 2
    storage = Armazenamento(url)
    if not storage.verificar():
        print('[ERRO] Nao conseguiu conectar/preparar banco. Revise host, SSL, senha, rede, extensao.')
        print('Codigo de diagnostico:', storage.erro)
        return 3
    try:
        conn = storage._conexao()
        versao = conn.execute("SELECT extversion FROM pg_extension WHERE extname='timescaledb'").fetchone()
        ht = conn.execute('''SELECT hypertable_name FROM timescaledb_information.hypertables
                             WHERE hypertable_name IN ('leituras','eventos_estado','comandos')''').fetchall()
        tabelas = {r[0] for r in ht}
        print('[OK] TimescaleDB versao:', versao[0] if versao else 'ausente')
        print('Hypertables:', ', '.join(sorted(tabelas)) or 'nenhuma')
        if tabelas != {'leituras', 'eventos_estado', 'comandos'}:
            print('[ERRO] Esquema incompleto. Confira usuario e permissoes CREATE EXTENSION/TABLE.')
            return 4
        for nome in ['leituras', 'eventos_estado', 'comandos']:
            # Nomes de tabela fixos, nunca fornecidos pelo usuario.
            total = conn.execute(f'SELECT count(*) FROM {nome}').fetchone()[0]
            print(f'[OK] {nome}: {total} registro(s)')
        recentes = conn.execute('''SELECT ts, lote_id, fc, g FROM leituras
                                  ORDER BY ts DESC LIMIT 3''').fetchall()
        for instante, lote, fc, g in recentes:
            print('Leitura:', instante.isoformat(), 'lote=', lote, 'FC=', fc, 'g=', g)
        print('[OK] Validacao concluida. Se leituras=0, conecte o Wokwi e rode novamente.')
        return 0
    except Exception as exc:
        print('[ERRO] Falha consultando as hypertables:', type(exc).__name__)
        return 5


if __name__ == '__main__':
    raise SystemExit(main())
