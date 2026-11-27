"""Integração contra um TimescaleDB real (não usa FakeHistorico).

O CI sobe o serviço Docker para este teste. Localmente, configure DATABASE_URL
para executar o mesmo teste; sem a variável ele é marcado como skipped.
"""
import os
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from armazenamento import Armazenamento  # noqa: E402


class TestarTimescaleDBReal(unittest.TestCase):
    def setUp(self):
        self.url = os.getenv('DATABASE_URL')
        if not self.url:
            self.skipTest('DATABASE_URL nao configurada; CI fornece TimescaleDB real')
        self.patient = 'ci-' + uuid.uuid4().hex
        self.device = 'ci-esp32-' + uuid.uuid4().hex[:8]
        self.store = Armazenamento(self.url)
        self.assertTrue(self.store.verificar(), 'TimescaleDB real precisa aceitar conexao')

    def tearDown(self):
        if not self.url:
            return
        with psycopg.connect(self.url, autocommit=True) as conn:
            conn.execute('DELETE FROM leituras WHERE patient_id = %s', (self.patient,))
            conn.execute('DELETE FROM eventos_estado WHERE patient_id = %s', (self.patient,))
            conn.execute('DELETE FROM comandos WHERE patient_id = %s', (self.patient,))
        if self.store.conn:
            self.store.conn.close()

    def test_grava_consulta_e_restaura_os_dados_persistidos(self):
        agora = datetime.now(timezone.utc)
        for indice in range(3):
            leituras = [
                {'fc': 120.0 + indice, 'g': 1.0},
                {'fc': 121.0 + indice, 'g': 1.0},
                {'fc': 122.0 + indice, 'g': 1.0},
            ]
            self.assertTrue(self.store.gravar_lote(
                self.patient, self.device, f'lote-{indice}', leituras,
                fim=agora + timedelta(seconds=indice * 3),
            ))

        evento = {
            'estado': 'ATENCAO',
            'razao': 'condicao_persistiu',
            'fcMedia': 121.0,
            'movimento': 'REST',
            'coberturaFc': 1.0,
            'coberturaMov': 1.0,
        }
        self.assertTrue(self.store.gravar_transicao(self.patient, evento))
        comando = {
            'commandId': 'cmd-ci-' + uuid.uuid4().hex[:8],
            'tipo': 'RECONHECER_ALERTA',
            'emitidoPor': 'cuidador01',
            'status': 'PENDENTE',
        }
        self.assertTrue(self.store.gravar_comando(self.patient, comando))

        historico_leituras = self.store.consultar(self.patient, limite=20)
        self.assertEqual(len(historico_leituras), 9)
        self.assertEqual(historico_leituras[0]['loteId'], 'lote-0')
        self.assertEqual(historico_leituras[-1]['loteId'], 'lote-2')

        snapshot = self.store.restaurar_estado(self.patient)
        self.assertIsNotNone(snapshot)
        self.assertEqual(len(snapshot['leituras']), 9)
        self.assertEqual(snapshot['historico'][-1]['estado'], 'ATENCAO')
        self.assertEqual(snapshot['historico'][-1]['razao'], 'condicao_persistiu')
        self.assertEqual(snapshot['comando']['commandId'], comando['commandId'])
        self.assertEqual(snapshot['comando']['status'], 'PENDENTE')

        comando['status'] = 'EXECUTADO'
        self.assertTrue(self.store.gravar_comando(self.patient, comando))
        snapshot = self.store.restaurar_estado(self.patient)
        self.assertEqual(snapshot['comando']['status'], 'EXECUTADO')
        self.assertIsNotNone(snapshot['comando']['confirmadoEmUtc'])


if __name__ == '__main__':
    unittest.main()
