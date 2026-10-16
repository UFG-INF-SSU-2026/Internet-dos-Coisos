"""Testes da API (sem Wokwi): python -m unittest discover -s marco3/testes -v"""
import hashlib
import os
import secrets
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from app import create_app  # noqa: E402

ESTADO = '/api/pacientes/patient-0042/estado'
COMANDO = '/api/pacientes/patient-0042/comando'
BUSCAR = '/api/dispositivo/comando?deviceId=esp32-borda-01&entityId=patient-0042'
ACK = '/api/dispositivo/comando/ack'


class TestarApi(unittest.TestCase):
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
        }
        with patch.dict(os.environ, env):
            self.client = TestClient(create_app())
        self.chave = {'X-Device-Key': env['DEVICE_API_KEY']}
        self.relogio = 1000.0
        patcher = patch('app.time.monotonic', lambda: self.relogio)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.client.close()

    def entrar(self, senha=None):
        return self.client.post('/login', data={'usuario': 'cuidador01', 'senha': senha or self.senha},
                                follow_redirects=False)

    def lote(self, n, fc=80, device='esp32-borda-01'):
        return {'deviceId': device, 'entityId': 'patient-0042', 'loteId': f'AB12CD34-{n}',
                'leituras': [{'fc': fc, 'g': 1.0}] * 3}

    def enviar_lotes(self, fc, quantidade):
        """Simula o ESP32 mandando um lote de 3 leituras a cada 3 s."""
        for _ in range(quantidade):
            self.relogio += 3
            r = self.client.post('/api/leituras', json=self.lote(int(self.relogio), fc), headers=self.chave)
            self.assertEqual(r.status_code, 200)
        return r.json()

    # ---------- autenticação e autorização do cuidador ----------
    def test_sem_login_nao_ve_paciente(self):
        self.assertEqual(self.client.get(ESTADO).status_code, 401)
        self.assertEqual(self.client.get('/painel', follow_redirects=False).status_code, 303)

    def test_login_errado_certo_e_logout(self):
        self.assertEqual(self.entrar('errada').status_code, 401)
        self.assertEqual(self.entrar().status_code, 303)
        self.assertEqual(self.client.get('/painel').status_code, 200)
        self.assertEqual(self.client.get(ESTADO).json()['estado'], 'SEM_DADOS')
        self.client.post('/logout')
        self.assertEqual(self.client.get(ESTADO).status_code, 401)

    def test_cuidador_nao_ve_outro_paciente(self):
        self.entrar()
        self.assertEqual(self.client.get('/api/pacientes/patient-9999/estado').status_code, 403)

    # ---------- autenticação e autorização do dispositivo ----------
    def test_chave_do_dispositivo(self):
        self.assertEqual(self.client.post('/api/leituras', json=self.lote(1)).status_code, 401)
        errada = {'X-Device-Key': 'errada'}
        self.assertEqual(self.client.post('/api/leituras', json=self.lote(1), headers=errada).status_code, 401)
        self.assertEqual(self.client.get(BUSCAR, headers=errada).status_code, 401)

    def test_dispositivo_nao_vinculado(self):
        r = self.client.post('/api/leituras', json=self.lote(1, device='esp32-intruso'), headers=self.chave)
        self.assertEqual(r.status_code, 403)
        r = self.client.get(BUSCAR.replace('esp32-borda-01', 'esp32-intruso'), headers=self.chave)
        self.assertEqual(r.status_code, 403)

    def test_lote_invalido(self):
        self.assertEqual(self.client.post('/api/leituras', content='nao-json', headers=self.chave).status_code, 400)
        sem_leituras = self.lote(1)
        sem_leituras['leituras'] = []
        self.assertEqual(self.client.post('/api/leituras', json=sem_leituras, headers=self.chave).status_code, 400)

    # ---------- ciclo 1 ----------
    def test_ciclo1_leituras_viram_estado_no_painel(self):
        self.entrar()
        self.assertEqual(self.enviar_lotes(80, 3)['estado'], 'NORMAL')
        r = self.client.post('/api/leituras', json=self.lote(int(self.relogio)), headers=self.chave)
        self.assertEqual(r.json()['status'], 'duplicado')
        self.assertEqual(self.enviar_lotes(120, 4)['estado'], 'ATENCAO')
        d = self.client.get(ESTADO).json()
        self.assertEqual(d['estado'], 'ATENCAO')
        self.assertEqual(d['lotesRecebidos'], 7)
        self.assertTrue(d['online'])
        self.assertEqual(d['historico'][0]['estado'], 'ATENCAO')

    def test_ciclo1_silencio_vira_dados_insuficientes(self):
        self.entrar()
        self.enviar_lotes(80, 3)
        self.relogio += 40                       # rede caiu: nenhum lote por 40 s
        d = self.client.get(ESTADO).json()
        self.assertEqual(d['estado'], 'DADOS_INSUFICIENTES')
        self.assertFalse(d['online'])

    # ---------- ciclo 2 ----------
    def test_ciclo2_comando_e_ack(self):
        self.entrar()
        self.assertEqual(self.client.post(COMANDO).status_code, 409)    # sem alerta
        self.enviar_lotes(120, 5)
        criado = self.client.post(COMANDO)
        self.assertEqual(criado.status_code, 201)
        self.assertEqual(self.client.post(COMANDO).status_code, 200)    # clique repetido
        cmd = criado.json()['commandId']
        ack = {'deviceId': 'esp32-borda-01', 'entityId': 'patient-0042', 'commandId': cmd}
        self.assertEqual(self.client.post(ACK, json=ack, headers=self.chave).status_code, 409)  # antes da entrega
        self.assertEqual(self.client.get(BUSCAR, headers=self.chave).json()['commandId'], cmd)
        self.assertEqual(self.client.get(ESTADO).json()['comando']['status'], 'ENTREGUE')
        self.assertEqual(self.client.post(ACK, json=ack, headers=self.chave).json()['status'], 'EXECUTADO')
        self.assertEqual(self.client.get(ESTADO).json()['comando']['status'], 'EXECUTADO')
        self.assertEqual(self.client.get(BUSCAR, headers=self.chave).json(), {})

    def test_ciclo2_quem_pode_o_que(self):
        self.enviar_lotes(120, 5)
        self.assertEqual(self.client.post(COMANDO, headers=self.chave).status_code, 401)  # ESP32 não cria comando
        self.entrar()
        self.assertEqual(self.client.post('/api/pacientes/patient-9999/comando').status_code, 403)
        cmd = self.client.post(COMANDO).json()['commandId']
        self.client.get(BUSCAR, headers=self.chave)
        ack = {'deviceId': 'esp32-borda-01', 'entityId': 'patient-0042', 'commandId': cmd}
        self.assertEqual(self.client.post(ACK, json=ack).status_code, 401)  # cuidador não forja ack


if __name__ == '__main__':
    unittest.main()
