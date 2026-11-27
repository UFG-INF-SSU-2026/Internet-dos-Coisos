"""Integração contra um TimescaleDB real (não usa FakeHistorico).

O CI sobe o serviço Docker para este teste. Localmente, configure DATABASE_URL
para executar o mesmo teste; sem a variável ele é marcado como skipped.
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from armazenamento import Armazenamento  # noqa: E402
from app import create_app  # noqa: E402


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


    def test_api_nova_restaura_alerta_e_entrega_comando_pendente(self):
        agora = datetime.now(timezone.utc)
        for indice in range(4):
            leituras = [{'fc': 120.0, 'g': 1.0}] * 3
            self.assertTrue(self.store.gravar_lote(
                self.patient, self.device, f'restart-{indice}', leituras,
                fim=agora + timedelta(seconds=indice * 3),
            ))

        evento = {
            'estado': 'ATENCAO', 'razao': 'condicao_persistiu',
            'fcMedia': 120.0, 'movimento': 'REST',
            'coberturaFc': 1.0, 'coberturaMov': 1.0,
        }
        self.assertTrue(self.store.gravar_transicao(self.patient, evento))
        comando = {
            'commandId': 'cmd-restart-' + uuid.uuid4().hex[:8],
            'tipo': 'RECONHECER_ALERTA', 'emitidoPor': 'cuidador01',
            'status': 'PENDENTE',
        }
        self.assertTrue(self.store.gravar_comando(self.patient, comando))

        senha = 'Senha-de-integracao-9!'
        sal = secrets.token_bytes(16)
        derivada = hashlib.scrypt(senha.encode(), salt=sal, n=2**14, r=8, p=1)
        chave = 'chave-ci-timescale-' + secrets.token_hex(20)
        env = {
            'APP_SECRET_KEY': 'segredo-ci-integracao-timescale-com-mais-de-32-bytes',
            'DEVICE_API_KEY': chave,
            'CUIDADOR_USUARIO': 'cuidador01',
            'CUIDADOR_SENHA_HASH': f'scrypt${sal.hex()}${derivada.hex()}',
            'DEVICE_ID': self.device,
            'PATIENT_ID': self.patient,
            'DATABASE_URL': self.url,
        }

        with patch.dict(os.environ, env):
            with TestClient(create_app()) as client:
                login = client.post('/login', data={'usuario': 'cuidador01', 'senha': senha}, follow_redirects=False)
                self.assertEqual(login.status_code, 303)

                estado = client.get(f'/api/pacientes/{self.patient}/estado')
                self.assertEqual(estado.status_code, 200)
                payload = estado.json()
                self.assertEqual(payload['estado'], 'ATENCAO')
                self.assertTrue(payload['online'])
                self.assertEqual(payload['comando']['commandId'], comando['commandId'])
                self.assertEqual(payload['comando']['status'], 'PENDENTE')
                self.assertEqual(len(payload['historicoLeituras']), 12)

                def assinatura(metodo, rota, corpo=b''):
                    timestamp = str(int(time.time()))
                    mensagem = f'{timestamp}\\n{metodo} {rota}\\n'.encode() + corpo
                    digest = hmac.new(chave.encode(), mensagem, hashlib.sha256).hexdigest()
                    return {'X-Timestamp': timestamp, 'X-Assinatura': digest}

                rota_comando = (
                    f'/api/dispositivo/comando?deviceId={self.device}&entityId={self.patient}'
                )
                entregue = client.get(rota_comando, headers=assinatura('GET', rota_comando))
                self.assertEqual(entregue.status_code, 200)
                self.assertEqual(entregue.json()['commandId'], comando['commandId'])

                ack = {
                    'deviceId': self.device,
                    'entityId': self.patient,
                    'commandId': comando['commandId'],
                }
                corpo = json.dumps(ack).encode()
                rota_ack = '/api/dispositivo/comando/ack'
                confirmado = client.post(
                    rota_ack, content=corpo,
                    headers={'Content-Type': 'application/json',
                             **assinatura('POST', rota_ack, corpo)},
                )
                self.assertEqual(confirmado.status_code, 200)
                self.assertEqual(confirmado.json()['status'], 'EXECUTADO')

                estado_final = client.get(f'/api/pacientes/{self.patient}/estado').json()
                self.assertEqual(estado_final['comando']['status'], 'EXECUTADO')



if __name__ == '__main__':
    unittest.main()
