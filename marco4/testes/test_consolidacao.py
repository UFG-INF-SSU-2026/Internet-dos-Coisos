"""Testa integracao da API com persistencia via fake, sem banco real.

Provar conexao com TimescaleDB de verdade ainda exige scripts/verificar_banco.py.
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

APIDIR = Path(__file__).resolve().parents[1] / 'api'
sys.path.insert(0, str(APIDIR))
import app
import gerar_config


class FakeHistorico:
    configurado = True
    ativo = True
    erro = None
    descartadas = 0
    def __init__(self):
        self.gravacoes = []
    def gravar_lote(self, device_id, patient_id, lote_id, leituras, estado):
        self.gravacoes.append(('lote', lote_id))
        return True
    def gravar_transicao(self, patient_id, evento):
        self.gravacoes.append(('transicao', evento['estado']))
        return True
    def gravar_comando(self, patient_id, comando):
        self.gravacoes.append(('comando', comando['status']))
        return True
    def consultar(self, patient_id, limite):
        return [{'recebidoEmUtc': '2026-11-06T12:00:00+00:00', 'loteId': 'abc',
                 'fc': 80, 'g': 1.0}]


class TestarPersistenciaIntegrada(unittest.TestCase):
    def setUp(self):
        sal = secrets.token_bytes(16)
        senha_hash = hashlib.scrypt(b'123456', salt=sal, n=2**14, r=8, p=1)
        self.chave = 'chave-de-teste-mais-de-vinte-e-quatro-caracteres'
        env = {'APP_SECRET_KEY': 'segredo-do-app-de-teste-mais-de-trinta-e-dois',
               'DEVICE_API_KEY': self.chave, 'CUIDADOR_USUARIO': 'cuidador01',
               'CUIDADOR_SENHA_HASH': f'scrypt${sal.hex()}${senha_hash.hex()}',
               'DEVICE_ID': 'esp32-borda-01', 'PATIENT_ID': 'patient-0042',
               'DATABASE_URL': 'postgresql://exemplo-falso/teste'}
        self.patch_env = patch.dict(os.environ, env)
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)
        self.hist = FakeHistorico()
        self.relogio = 1000.0
        self.patch_relogio = patch('app.time.monotonic', lambda: self.relogio)
        self.patch_relogio.start()
        self.addCleanup(self.patch_relogio.stop)
        with patch.object(app, 'HistoricoTemporal', return_value=self.hist):
            self.client = TestClient(app.create_app())
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def postar(self, n, fc=80):
        self.relogio += 3
        body = json.dumps({'deviceId':'esp32-borda-01','entityId':'patient-0042',
                           'loteId':f'teste-{n}','leituras':[{'fc':fc,'g':1.0}]*3}).encode()
        ts = str(int(time.time()))
        assinatura = hmac.new(self.chave.encode(),f'{ts}\nPOST /api/leituras\n'.encode()+body,
                             hashlib.sha256).hexdigest()
        return self.client.post('/api/leituras',content=body,headers={'X-Timestamp':ts,'X-Assinatura':assinatura})

    def assinar_get(self, rota):
        ts = str(int(time.time()))
        assinatura = hmac.new(self.chave.encode(), f'{ts}\nGET {rota}\n'.encode(),
                              hashlib.sha256).hexdigest()
        return {'X-Timestamp':ts,'X-Assinatura':assinatura}

    def assinar_post(self, rota, dados):
        corpo = json.dumps(dados).encode()
        ts = str(int(time.time()))
        ass = hmac.new(self.chave.encode(), f'{ts}\nPOST {rota}\n'.encode()+corpo,
                       hashlib.sha256).hexdigest()
        return self.client.post(rota, content=corpo, headers={'X-Timestamp':ts,'X-Assinatura':ass})

    def test_grava_leituras_transicoes_e_retorna_historico(self):
        self.client.post('/login', data={'usuario':'cuidador01','senha':'123456'})
        for n in range(1,4):
            self.assertEqual(self.postar(n).status_code,200)
        kinds = [tipo for tipo,*_ in self.hist.gravacoes]
        self.assertEqual(kinds.count('lote'),3)
        self.assertIn('transicao',kinds)
        r = self.client.get('/api/pacientes/patient-0042/historico')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['origem'],'TimescaleDB')
        self.assertEqual(r.json()['leituras'][0]['loteId'],'abc')

    def test_grava_atuacoes_no_segundo_ciclo(self):
        self.client.post('/login', data={'usuario':'cuidador01','senha':'123456'})
        for n in range(1,6):
            self.assertEqual(self.postar(n,fc=120).status_code,200)
        r = self.client.post('/api/pacientes/patient-0042/comando')
        self.assertEqual(r.status_code,201)
        cid = r.json()['commandId']
        rota = '/api/dispositivo/comando?deviceId=esp32-borda-01&entityId=patient-0042'
        self.assertEqual(self.client.get(rota,headers=self.assinar_get(rota)).status_code,200)
        ack = {'deviceId':'esp32-borda-01','entityId':'patient-0042','commandId':cid}
        r = self.assinar_post('/api/dispositivo/comando/ack',ack)
        self.assertEqual(r.json()['status'],'EXECUTADO')
        estados = [valor for tipo,valor in self.hist.gravacoes if tipo == 'comando']
        self.assertEqual(estados,['PENDENTE','ENTREGUE','EXECUTADO'])


class TestarCredenciaisPrivadas(unittest.TestCase):
    def test_gera_config_e_preserva_em_segunda_execucao(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            env = folder/'api/.env'; config = folder/'produtor/config.h'
            env.parent.mkdir();config.parent.mkdir()
            with patch.object(gerar_config,'ENV',env), patch.object(gerar_config,'CONFIG_ESP32',config):
                gerar_config.main()
                orig_env,orig_config=env.read_text(),config.read_text()
                self.assertIn('DEVICE_API_KEY=',orig_env)
                self.assertIn(orig_env.split('DEVICE_API_KEY=')[1].splitlines()[0],orig_config)
                gerar_config.main()
                self.assertEqual(env.read_text(),orig_env)
                self.assertEqual(config.read_text(),orig_config)

    def test_recria_config_esp32_quando_env_ja_existe(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);env=folder/'api/.env';config=folder/'produtor/config.h'
            env.parent.mkdir();config.parent.mkdir()
            env.write_text('DEVICE_API_KEY=chave-importada-do-projeto-123456\nDATABASE_URL=postgresql://fake\n')
            with patch.object(gerar_config,'ENV',env), patch.object(gerar_config,'CONFIG_ESP32',config):
                gerar_config.main()
                self.assertIn('chave-importada-do-projeto-123456',config.read_text())
                self.assertIn('DATABASE_URL=postgresql://fake',env.read_text())


if __name__ == '__main__':
    unittest.main()
