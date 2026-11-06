"""Persistencia TimescaleDB, consolidada a partir da branch ``timescaledb`` do grupo.

Responsabilidades isoladas: criar hypertables, gravar leituras, transicoes de estado,
comandos/ACKs e consultar historico. Sem banco, a API continua em memoria, mas
nao demonstra persistencia. Nao e uma fila duravel: perdas durante indisponibilidade
sao explicitamente registradas como limitacao didatica.
"""

import threading
import time
from datetime import datetime, timedelta, timezone

import psycopg

PAUSA_S = 15
CONEXAO_TIMEOUT_S = 3


def _num(valor):
    """Conserva valores numericos da simulacao, descartando nao numericos."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


class Armazenamento:
    def __init__(self, url):
        self.url = url
        self.trava = threading.Lock()
        self.conn = None
        self.pausa_ate = 0.0
        self.fora_do_ar = False
        self.ativo = False
        self.erro = None
        self.gravacoes_descartadas = 0

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

    def _rodar(self, funcao, *, gravacao=False):
        """Executa funcao(conn), com reconexao e falha controlada sem expor DSN."""
        with self.trava:
            if time.monotonic() < self.pausa_ate:
                if gravacao:
                    self.gravacoes_descartadas += 1
                return None
            tentativas = 2 if self.conn is not None and not self.conn.closed else 1
            ultimo_erro = None
            for _ in range(tentativas):
                try:
                    resultado = funcao(self._conexao())
                except psycopg.Error as exc:
                    ultimo_erro = exc
                    self._descartar()
                    continue
                if self.fora_do_ar:
                    print('[armazenamento] TimescaleDB voltou: operacoes retomadas')
                self.fora_do_ar = False
                self.ativo = True
                self.erro = None
                return resultado
            self.ativo = False
            self.erro = f'{type(ultimo_erro).__name__}: TimescaleDB indisponivel'
            self.pausa_ate = time.monotonic() + PAUSA_S
            if gravacao:
                self.gravacoes_descartadas += 1
            if not self.fora_do_ar:
                print(f'[armazenamento] {self.erro}; API segue em memoria, sem persistir durante a falha')
            self.fora_do_ar = True
            return None

    def verificar(self):
        """Conecta, confere a extensao e prepara as tabelas na primeira chamada."""
        return self._rodar(lambda conn: bool(conn.execute('SELECT 1').fetchone())) is True

    @staticmethod
    def _criar_tabelas(conn):
        # Em Tiger Cloud a extensao normalmente ja esta ativa; em PostgreSQL com
        # a extensao instalada, este comando habilita no banco atual.
        conn.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')
        conn.execute('''CREATE TABLE IF NOT EXISTS leituras (
            ts TIMESTAMPTZ NOT NULL, patient_id TEXT NOT NULL, device_id TEXT NOT NULL,
            lote_id TEXT NOT NULL, fc DOUBLE PRECISION, g DOUBLE PRECISION)''')
        conn.execute("SELECT create_hypertable('leituras', 'ts', if_not_exists => TRUE)")
        conn.execute('''CREATE INDEX IF NOT EXISTS idx_leituras_paciente_tempo
                        ON leituras(patient_id, ts DESC)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS eventos_estado (
            ts TIMESTAMPTZ NOT NULL, patient_id TEXT NOT NULL, estado TEXT NOT NULL,
            razao TEXT, fc_media DOUBLE PRECISION, movimento TEXT,
            cobertura_fc DOUBLE PRECISION, cobertura_mov DOUBLE PRECISION)''')
        conn.execute("SELECT create_hypertable('eventos_estado', 'ts', if_not_exists => TRUE)")
        conn.execute('''CREATE INDEX IF NOT EXISTS idx_eventos_paciente_tempo
                        ON eventos_estado(patient_id, ts DESC)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS comandos (
            ts TIMESTAMPTZ NOT NULL, patient_id TEXT NOT NULL, command_id TEXT NOT NULL,
            tipo TEXT NOT NULL, status TEXT NOT NULL, emitido_por TEXT)''')
        conn.execute("SELECT create_hypertable('comandos', 'ts', if_not_exists => TRUE)")
        conn.execute('''CREATE INDEX IF NOT EXISTS idx_comandos_paciente_tempo
                        ON comandos(patient_id, ts DESC)''')

    def gravar_lote(self, patient_id, device_id, lote_id, leituras, fim=None):
        """Grava as leituras em intervalos de 1 s; ignora lote ja persistido.

        ``fim`` e horario de recebimento: o hardware nao envia timestamps individuais.
        """
        if fim is None:
            fim = datetime.now(timezone.utc)

        def gravar(conn):
            with conn.transaction():
                if conn.execute('''SELECT 1 FROM leituras WHERE lote_id = %s AND
                                   patient_id = %s AND device_id = %s LIMIT 1''',
                                (lote_id, patient_id, device_id)).fetchone():
                    return True
                n = len(leituras)
                linhas = [(fim - timedelta(seconds=n - 1 - i), patient_id, device_id,
                           lote_id, _num(l.get('fc')), _num(l.get('g')))
                          for i, l in enumerate(leituras)]
                with conn.cursor() as cur:
                    cur.executemany('''INSERT INTO leituras
                        (ts, patient_id, device_id, lote_id, fc, g)
                        VALUES (%s, %s, %s, %s, %s, %s)''', linhas)
            return True

        return self._rodar(gravar, gravacao=True) is True

    def gravar_transicao(self, patient_id, evento, ts=None):
        ts = ts or datetime.now(timezone.utc)
        def gravar(conn):
            conn.execute('''INSERT INTO eventos_estado
                (ts, patient_id, estado, razao, fc_media, movimento, cobertura_fc, cobertura_mov)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                (ts, patient_id, evento['estado'], evento.get('razao'), evento.get('fcMedia'),
                 evento.get('movimento'), evento.get('coberturaFc'), evento.get('coberturaMov')))
            return True
        return self._rodar(gravar, gravacao=True) is True

    def gravar_comando(self, patient_id, comando, ts=None):
        ts = ts or datetime.now(timezone.utc)
        def gravar(conn):
            conn.execute('''INSERT INTO comandos
                (ts, patient_id, command_id, tipo, status, emitido_por)
                VALUES (%s, %s, %s, %s, %s, %s)''',
                (ts, patient_id, comando['commandId'], comando['tipo'],
                 comando['status'], comando['emitidoPor']))
            return True
        return self._rodar(gravar, gravacao=True) is True

    def consultar(self, patient_id, limite=100):
        """Leituras mais recentes, ordenadas da mais antiga para a mais nova."""
        limite = min(500, max(1, int(limite)))
        def buscar(conn):
            rows = conn.execute('''SELECT ts, lote_id, fc, g FROM leituras
                                   WHERE patient_id = %s ORDER BY ts DESC LIMIT %s''',
                                (patient_id, limite)).fetchall()
            return [{'recebidoEmUtc': ts.isoformat(), 'loteId': lote,
                     'fc': fc, 'g': g} for ts, lote, fc, g in reversed(rows)]
        return self._rodar(buscar)
