"""Marco 3: armazenamento temporal (TimescaleDB). Só persistência: sem regra, HTTP ou login.

O banco é um extra: se ele estiver fora do ar (Docker parado, por exemplo), a API
continua funcionando em memória. Este módulo:
  - nunca conecta ao ser importado nem ao iniciar a API;
  - conecta na primeira gravação (e cria as tabelas se faltarem);
  - se a conexão falhar, avisa UMA vez no terminal, descarta as gravações e só
    tenta de novo depois de PAUSA_S segundos (a API não fica lenta nem enche o
    terminal de erros);
  - ao voltar, reconecta sozinho e avisa.
Gravações feitas enquanto o banco estava fora são perdidas (sem fila, como na
decisão D12): o estado em memória continua correto.
"""

import threading
import time
from datetime import timedelta

import psycopg

PAUSA_S = 15            # depois de uma falha, espera isso antes de tentar de novo
CONEXAO_TIMEOUT_S = 2   # não deixa uma resposta ao ESP32 esperando muito pelo banco


def _num(valor):
    """Número como veio do ESP32 (mesmo fora de faixa, para auditoria) ou None."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def _resumo(erro):
    return ' '.join(str(erro).split())[:160]


class Armazenamento:
    def __init__(self, url):
        self.url = url
        self.trava = threading.Lock()   # as gravações rodam em threads (asyncio.to_thread)
        self.conn = None
        self.pausa_ate = 0.0            # relógio monotônico: até quando não tentar conectar
        self.fora_do_ar = False         # já avisamos que o banco está indisponível?

    # ---------------- conexão ----------------
    def _conexao(self):
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(self.url, autocommit=True,
                                        connect_timeout=CONEXAO_TIMEOUT_S)
            self._criar_tabelas(self.conn)
        return self.conn

    def _descartar(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except psycopg.Error:
                pass
        self.conn = None

    def _rodar(self, funcao):
        """Executa funcao(conn). Se o banco estiver indisponível, devolve None sem levantar erro."""
        with self.trava:
            if time.monotonic() < self.pausa_ate:
                return None
            # Com conexão já aberta, uma 2ª tentativa cobre o caso do banco ter reiniciado.
            tentativas = 2 if self.conn is not None and not self.conn.closed else 1
            ultimo_erro = None
            for _ in range(tentativas):
                try:
                    resultado = funcao(self._conexao())
                except psycopg.Error as erro:
                    ultimo_erro = erro
                    self._descartar()
                    continue
                if self.fora_do_ar:
                    print('[armazenamento] banco voltou: gravacao retomada')
                    self.fora_do_ar = False
                return resultado
            self.pausa_ate = time.monotonic() + PAUSA_S
            if not self.fora_do_ar:
                print(f'[armazenamento] banco indisponivel ({_resumo(ultimo_erro)}). '
                      f'A API segue em memoria; nova tentativa em {PAUSA_S} s.')
                self.fora_do_ar = True
            return None

    def verificar(self):
        """Tenta conectar agora (usado ao iniciar, só para informar). Nunca levanta erro."""
        return self._rodar(lambda conn: conn.execute('SELECT 1').fetchone()) is not None

    # ---------------- esquema ----------------
    @staticmethod
    def _criar_tabelas(conn):
        conn.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leituras (
                ts TIMESTAMPTZ NOT NULL, patient_id TEXT NOT NULL, device_id TEXT NOT NULL,
                lote_id TEXT NOT NULL, fc DOUBLE PRECISION, g DOUBLE PRECISION)""")
        conn.execute("SELECT create_hypertable('leituras', 'ts', if_not_exists => TRUE)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eventos_estado (
                ts TIMESTAMPTZ NOT NULL, patient_id TEXT NOT NULL, estado TEXT NOT NULL,
                razao TEXT, fc_media DOUBLE PRECISION, movimento TEXT,
                cobertura_fc DOUBLE PRECISION, cobertura_mov DOUBLE PRECISION)""")
        conn.execute("SELECT create_hypertable('eventos_estado', 'ts', if_not_exists => TRUE)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comandos (
                ts TIMESTAMPTZ NOT NULL, patient_id TEXT NOT NULL, command_id TEXT NOT NULL,
                tipo TEXT NOT NULL, status TEXT NOT NULL, emitido_por TEXT)""")
        conn.execute("SELECT create_hypertable('comandos', 'ts', if_not_exists => TRUE)")

    # ---------------- gravações ----------------
    def gravar_lote(self, patient_id, device_id, lote_id, leituras, fim):
        """A última leitura do lote é a mais recente (= fim); as anteriores, 1 s antes cada."""
        def gravar(conn):
            # Lote já gravado (reenvio depois de reiniciar a API): não duplica.
            if conn.execute('SELECT 1 FROM leituras WHERE lote_id = %s LIMIT 1',
                            (lote_id,)).fetchone():
                return
            n = len(leituras)
            linhas = [(fim - timedelta(seconds=n - 1 - i), patient_id, device_id, lote_id,
                       _num(l.get('fc')), _num(l.get('g'))) for i, l in enumerate(leituras)]
            with conn.cursor() as cur:
                cur.executemany('INSERT INTO leituras VALUES (%s, %s, %s, %s, %s, %s)', linhas)
        self._rodar(gravar)

    def gravar_transicao(self, patient_id, evento, ts):
        self._rodar(lambda conn: conn.execute(
            'INSERT INTO eventos_estado VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (ts, patient_id, evento['estado'], evento.get('razao'), evento.get('fcMedia'),
             evento.get('movimento'), evento.get('coberturaFc'), evento.get('coberturaMov'))))

    def gravar_comando(self, patient_id, comando, ts):
        self._rodar(lambda conn: conn.execute(
            'INSERT INTO comandos VALUES (%s, %s, %s, %s, %s, %s)',
            (ts, patient_id, comando['commandId'], comando['tipo'],
             comando['status'], comando['emitidoPor'])))
