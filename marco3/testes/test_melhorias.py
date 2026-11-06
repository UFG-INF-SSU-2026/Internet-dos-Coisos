"""Testes do WebSocket, fila e historico local (nao exigem TimescaleDB)."""
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from app import create_app


class TestarMelhorias(unittest.TestCase):
    def setUp(self):
        sal = secrets.token_bytes(16)
        senha_hash = hashlib.scrypt(b'minha-senha', salt=sal, n=2**14, r=8, p=1)
        self.chave = 'chave-de-teste-para-o-dispositivo-com-privilégios'
        env = {
            'APP_SECRET_KEY': 'chave-da-sessao-de-teste-bem-comprida-1234567',
            'DEVICE_API_KEY': self.chave,
            'CUIDADOR_USUARIO': 'cuidador01',
            'CUIDADOR_SENHA_HASH': f'scrypt${sal.hex()}${senha_hash.hex()}',
            'DEVICE_ID': 'esp32-borda-01',
            'PATIENT_ID': 'patient-0042',
            'DATABASE_URL': '',
        }
        self.env_patch = patch.dict(os.environ, env)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.client = TestClient(create_app())
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def login(self):
        r = self.client.post('/login', data={'usuario': 'cuidador01', 'senha': 'minha-senha'})
        self.assertEqual(r.status_code, 200)

    def postar(self, numero=1):
        url = '/api/leituras'
        corpo = json.dumps({'deviceId': 'esp32-borda-01', 'entityId': 'patient-0042',
                            'loteId': f'lote-{numero}',
                            'leituras': [{'fc': 80, 'g': 1.0}] * 3}).encode()
        ts = str(int(time.time()))
        msg = f'{ts}\nPOST {url}\n'.encode() + corpo
        assinatura = hmac.new(self.chave.encode(), msg, hashlib.sha256).hexdigest()
        return self.client.post(url, content=corpo, headers={
            'X-Timestamp': ts, 'X-Assinatura': assinatura, 'Content-Type': 'application/json'})

    def test_endpoint_saude_sem_dados_pessoais(self):
        resposta = self.client.get('/api/saude')
        self.assertEqual(resposta.status_code, 200)
        d = resposta.json()
        self.assertEqual(d['servico'], 'online')
        self.assertNotIn('paciente', d)
        self.assertFalse(d['banco_configurado'])

    def test_fila_evidencia_ordem_e_contadores(self):
        self.login()
        for n in range(1, 4):
            self.assertEqual(self.postar(numero=n).status_code, 200)
        estado = self.client.get('/api/pacientes/patient-0042/estado').json()
        self.assertEqual(estado['fila']['pendentes'], 0)
        self.assertEqual(estado['fila']['enfileirados'], 3)
        self.assertEqual(estado['fila']['processados'], 3)
        self.assertEqual([x['loteId'] for x in estado['fila']['ultimosLotesProcessados']],
                         ['lote-1', 'lote-2', 'lote-3'])

    def test_websocket_precisa_sessao(self):
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect('/ws/pacientes/patient-0042') as ws:
                ws.receive_json()
        self.assertEqual(ctx.exception.code, 1008)

    def test_fila_processa_e_preserva_estado(self):
        self.login()
        r = self.postar()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'recebido')
        estado = self.client.get('/api/pacientes/patient-0042/estado').json()
        self.assertEqual(estado['fila']['enfileirados'], 1)
        self.assertEqual(estado['fila']['processados'], 1)
        self.assertEqual(len(estado['historicoLeituras']), 3)
        self.assertEqual(estado['persistenciaTemporal'], 'nao_configurada')
        historico = self.client.get('/api/pacientes/patient-0042/historico').json()
        self.assertEqual(historico['origem'], 'memoria (nao persistente)')
        self.assertEqual(len(historico['leituras']), 3)
        self.assertEqual(self.postar().json()['status'], 'duplicado')
        self.assertEqual(self.client.get('/api/pacientes/patient-0042/estado').json()['fila']['processados'], 1)

    def test_websocket_envia_estado_ao_receber_leituras(self):
        self.login()
        with self.client.websocket_connect('/ws/pacientes/patient-0042') as ws:
            inicial = ws.receive_json()
            self.assertEqual(inicial['estado'], 'SEM_DADOS')
            r = self.postar()
            self.assertEqual(r.status_code, 200)
            atualizado = ws.receive_json()
            self.assertEqual(atualizado['lotesRecebidos'], 1)
            self.assertEqual(atualizado['fila']['processados'], 1)

    def test_historico_protegido(self):
        self.assertEqual(self.client.get('/api/pacientes/patient-0042/historico').status_code, 401)
        self.login()
        self.assertEqual(self.client.get('/api/pacientes/outro/historico').status_code, 403)


if __name__ == '__main__':
    unittest.main()
