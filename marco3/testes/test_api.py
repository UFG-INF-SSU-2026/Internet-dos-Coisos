"""Testes do Marco 3 (sem Wokwi): python -m unittest discover -s marco3/testes -v"""
import hashlib
import os
import re
import secrets
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from app import create_app  # noqa: E402


class TestarMarco3(unittest.TestCase):
    def setUp(self):
        self.senha = 'Senha-de-aula-9!'
        sal = secrets.token_bytes(16)
        derivada = hashlib.scrypt(self.senha.encode(), salt=sal, n=2**14, r=8, p=1)
        env = {
            'APP_SECRET_KEY': 'teste-servidor-possui-chave-grande-para-assinatura-123',
            'DEVICE_API_KEY': 'chave-esp32-para-teste-super-grande',
            'CUIDADOR_USUARIO': 'cuidador01',
            'CUIDADOR_SENHA_HASH': f'scrypt${sal.hex()}${derivada.hex()}',
            'DEVICE_ID': 'esp32-borda-01',
            'PATIENT_ID': 'patient-0042',
            'COOKIE_SECURE': '0',
        }
        with patch.dict(os.environ, env):
            self.client = TestClient(create_app())
        self.headers = {'X-Device-Key': env['DEVICE_API_KEY']}

    def tearDown(self):
        self.client.close()

    def evento(self, seq=1, boot='AB12CD34', estado='NORMAL'):
        return {
            'schemaVersion': 2, 'eventType': 'vitals.state.changed',
            'eventId': f'esp32-borda-01-{boot}-{seq}',
            'deviceId': 'esp32-borda-01', 'entityId': 'patient-0042',
            'bootId': boot, 'eventTimeMs': 76082+seq, 'sequence': seq,
            'value': 88.0, 'unit': 'bpm', 'state': estado, 'motion': 'REST',
            'coverageFc': 1.0, 'coverageMov': 1.0, 'reason': 'janela_com_cobertura',
        }

    def csrf(self, caminho='/login'):
        html = self.client.get(caminho).text
        resultado = re.search(r'name="csrf" value="([^"]+)"', html)
        self.assertIsNotNone(resultado)
        return resultado.group(1)

    def entrar(self):
        token = self.csrf()
        r = self.client.post('/login', data={
            'csrf': token, 'usuario': 'cuidador01', 'senha': self.senha,
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers['location'], '/painel')

    def test_sem_login_nao_ve_paciente(self):
        self.assertEqual(self.client.get('/api/pacientes/patient-0042/estado').status_code, 401)
        self.assertEqual(self.client.get('/painel', follow_redirects=False).status_code, 303)

    def test_login_e_logout(self):
        token = self.csrf()
        errado = self.client.post('/login', data={'csrf':token,'usuario':'cuidador01','senha':'errada'})
        self.assertEqual(errado.status_code, 401)
        self.entrar()
        self.assertEqual(self.client.get('/painel').status_code, 200)
        self.assertEqual(self.client.get('/api/pacientes/patient-0042/estado').status_code, 200)
        token = self.csrf('/painel')
        self.assertEqual(self.client.post('/logout', data={'csrf': token}, follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get('/api/pacientes/patient-0042/estado').status_code, 401)

    def test_formulario_sem_csrf(self):
        self.assertEqual(self.client.post('/login',data={'usuario':'cuidador01','senha':self.senha}).status_code,400)

    def test_chave_de_dispositivo(self):
        self.assertEqual(self.client.post('/api/eventos',json=self.evento()).status_code,401)
        self.assertEqual(self.client.post('/api/eventos',json=self.evento(), headers={'X-Device-Key':'errado'}).status_code,401)
        self.assertEqual(self.client.post('/api/eventos',json=self.evento(), headers=self.headers).status_code,201)

    def test_associacao_produtor_paciente(self):
        e = self.evento()
        e['entityId'] = 'patient-9999'
        self.assertEqual(self.client.post('/api/eventos',json=e,headers=self.headers).status_code,403)
        self.entrar()
        self.assertEqual(self.client.get('/api/pacientes/patient-9999/estado').status_code,403)

    def test_contrato_invalido(self):
        e=self.evento()
        e['schemaVersion']=1
        self.assertEqual(self.client.post('/api/eventos',json=e,headers=self.headers).status_code,400)
        e=self.evento()
        e['coverageFc']=9
        self.assertEqual(self.client.post('/api/eventos',json=e,headers=self.headers).status_code,400)
        self.assertEqual(self.client.post('/api/eventos',data='nao-json',headers=self.headers).status_code,400)

    def test_eventos_deduplicacao_e_saltos(self):
        self.entrar()
        r=self.client.post('/api/eventos',json=self.evento(1),headers=self.headers)
        self.assertEqual(r.status_code,201)
        r=self.client.post('/api/eventos',json=self.evento(1),headers=self.headers)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['status'],'duplicado')
        r=self.client.post('/api/eventos',json=self.evento(3,estado='ATENCAO'),headers=self.headers)
        self.assertEqual(r.status_code,201)
        d=self.client.get('/api/pacientes/patient-0042/estado').json()
        self.assertEqual(d['estado'],'ATENCAO')
        self.assertEqual(d['eventosRecebidos'],2)
        self.assertEqual(d['eventosDuplicados'],1)
        self.assertEqual(d['saltosDeSequencia'],1)
        self.assertTrue(d['online'])
        self.assertEqual(self.client.post('/api/eventos',json=self.evento(2),headers=self.headers).status_code,409)

    def test_reinicio_do_esp32(self):
        self.assertEqual(self.client.post('/api/eventos',json=self.evento(5),headers=self.headers).status_code,201)
        self.assertEqual(self.client.post('/api/eventos',json=self.evento(1,boot='DEADBEEF'),headers=self.headers).status_code,201)
        self.assertEqual(self.client.post('/api/eventos',json=self.evento(6),headers=self.headers).status_code,409)

    def test_heartbeat(self):
        self.entrar()
        cab={'deviceId':'esp32-borda-01','entityId':'patient-0042','bootId':'AB12CD34'}
        self.assertEqual(self.client.post('/api/heartbeat',json=cab,headers=self.headers).status_code,200)
        d=self.client.get('/api/pacientes/patient-0042/estado').json()
        self.assertTrue(d['online'])
        self.assertEqual(d['estado'],'SEM_EVENTOS')


if __name__ == '__main__':
    unittest.main()
