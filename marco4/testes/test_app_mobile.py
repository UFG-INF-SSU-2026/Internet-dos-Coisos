"""Marco 4: testes das rotas do app Android (token, segundo produtor, contexto).

Rodar: python -m unittest -v test_app_mobile   (dentro de marco4/testes)
"""
import hashlib
import json
import os
import secrets
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from app import create_app  # noqa: E402
from regra import Monitor  # noqa: E402
from test_api import CHAVE, assinar  # noqa: E402

SEGREDO = 'teste-servidor-possui-chave-grande-para-assinatura-123'
ESTADO = '/api/pacientes/patient-0042/estado'
COMANDO = '/api/pacientes/patient-0042/comando'


class TestarAppMobile(unittest.TestCase):
    def setUp(self):
        self.senha = 'Senha-de-aula-9!'
        sal = secrets.token_bytes(16)
        derivada = hashlib.scrypt(self.senha.encode(), salt=sal, n=2**14, r=8, p=1)
        env = {
            'APP_SECRET_KEY': SEGREDO,
            'DEVICE_API_KEY': CHAVE,
            'CUIDADOR_USUARIO': 'cuidador01',
            'CUIDADOR_SENHA_HASH': f'scrypt${sal.hex()}${derivada.hex()}',
            'DEVICE_ID': 'esp32-borda-01',
            'PATIENT_ID': 'patient-0042',
            'DATABASE_URL': '',
        }
        with patch.dict(os.environ, env):
            self.client = TestClient(create_app())
        self.relogio = 1000.0
        patcher = patch('app.time.monotonic', lambda: self.relogio)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.seq_ms = 0

    def tearDown(self):
        self.client.close()

    # ---------- ajudantes ----------
    def login_app(self, senha=None):
        return self.client.post('/api/app/login',
                                json={'usuario': 'cuidador01', 'senha': senha or self.senha})

    def cabecalho(self, token):
        return {'Authorization': f'Bearer {token}'}

    def token(self):
        r = self.login_app()
        self.assertEqual(r.status_code, 200)
        return r.json()['token']

    def movimento(self, token, intensidade, atraso_s=0.0, entidade='patient-0042'):
        """Simula o app: leitura do acelerômetro com o horário de captura."""
        self.seq_ms += 1     # garante capturadoEmMs crescente dentro do mesmo milissegundo
        capturado = int((time.time() - atraso_s) * 1000) + self.seq_ms
        return self.client.post('/api/app/leituras', headers=self.cabecalho(token), json={
            'entityId': entidade, 'intensidade': intensidade, 'capturadoEmMs': capturado})

    def lote_esp32(self, fc):
        self.relogio += 3
        corpo = json.dumps({'deviceId': 'esp32-borda-01', 'entityId': 'patient-0042',
                            'loteId': f'AB12CD34-{int(self.relogio)}',
                            'leituras': [{'fc': fc, 'g': 1.0}] * 3}).encode()
        r = self.client.post('/api/leituras', content=corpo, headers={
            'Content-Type': 'application/json', **assinar('POST', '/api/leituras', corpo)})
        self.assertEqual(r.status_code, 200)
        return r.json()

    # ---------- autenticação: token ----------
    def test_login_app_devolve_token_e_senha_errada_401(self):
        self.assertEqual(self.login_app('errada').status_code, 401)
        self.assertEqual(self.client.post('/api/app/login', content=b'nao-json').status_code, 400)
        d = self.login_app().json()
        self.assertEqual(d['tipo'], 'Bearer')
        self.assertEqual(d['paciente'], 'patient-0042')
        r = self.client.get(ESTADO, headers=self.cabecalho(d['token']))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['estado'], 'SEM_DADOS')
        self.assertNotIn('set-cookie', r.headers)      # o app não depende de cookie

    def test_token_invalido_401(self):
        forjado = URLSafeTimedSerializer('outro-segredo-qualquer-com-32-caracteres!',
                                         salt='coisos-app-token-v1').dumps(
            {'u': 'cuidador01', 'p': 'patient-0042'})
        for cabecalho in ({'Authorization': 'Bearer lixo'},
                          {'Authorization': 'Bearer '},
                          {'Authorization': f'Basic {self.token()}'},
                          self.cabecalho(forjado)):
            with self.subTest(cabecalho=cabecalho['Authorization'][:12]):
                self.assertEqual(self.client.get(ESTADO, headers=cabecalho).status_code, 401)
                self.assertEqual(self.client.post(COMANDO, headers=cabecalho).status_code, 401)
                r = self.client.post('/api/app/leituras', headers=cabecalho, json={
                    'entityId': 'patient-0042', 'intensidade': 0.5,
                    'capturadoEmMs': int(time.time() * 1000)})
                self.assertEqual(r.status_code, 401)

    def test_token_expirado_401(self):
        token = self.token()
        with patch('app.TOKEN_APP_VALIDADE_S', -1):
            self.assertEqual(self.client.get(ESTADO, headers=self.cabecalho(token)).status_code, 401)

    def test_token_de_outro_paciente_403(self):
        cab = self.cabecalho(self.token())
        self.assertEqual(self.client.get('/api/pacientes/patient-9999/estado', headers=cab).status_code, 403)
        self.assertEqual(self.client.get('/api/pacientes/patient-9999/historico', headers=cab).status_code, 403)
        self.assertEqual(self.client.post('/api/pacientes/patient-9999/comando', headers=cab).status_code, 403)
        self.assertEqual(self.movimento(self.token(), 0.5, entidade='patient-9999').status_code, 403)

    # ---------- segundo produtor: leituras do celular ----------
    def test_leitura_do_celular_atrasada_e_rejeitada(self):
        token = self.token()
        atrasada = self.movimento(token, 0.6, atraso_s=15)
        self.assertEqual(atrasada.status_code, 422)
        self.assertEqual(atrasada.json()['motivo'], 'atrasada')
        adiantada = self.movimento(token, 0.6, atraso_s=-30)
        self.assertEqual(adiantada.json()['motivo'], 'relogio_adiantado')
        self.assertEqual(self.movimento(token, 0.6).status_code, 200)
        self.seq_ms -= 50                                  # chega uma leitura mais antiga
        fora = self.movimento(token, 0.6)
        self.assertEqual(fora.status_code, 422)
        self.assertEqual(fora.json()['motivo'], 'fora_de_ordem')
        cel = self.client.get(ESTADO, headers=self.cabecalho(token)).json()['celular']
        self.assertEqual((cel['recebidas'], cel['descartadas']), (1, 3))

    def test_leitura_do_celular_invalida_400(self):
        cab = self.cabecalho(self.token())
        for corpo in ({'entityId': 'patient-0042', 'intensidade': 'alta', 'capturadoEmMs': 1},
                      {'entityId': 'patient-0042', 'intensidade': 0.3},
                      {'entityId': 'patient-0042', 'intensidade': 99, 'capturadoEmMs': 1}):
            self.assertEqual(self.client.post('/api/app/leituras', headers=cab, json=corpo).status_code, 400)

    def test_leituras_do_celular_passam_pela_fila(self):
        token = self.token()
        self.lote_esp32(80)
        self.assertEqual(self.movimento(token, 0.6).json()['status'], 'recebido')
        fila = self.client.get(ESTADO, headers=self.cabecalho(token)).json()['fila']
        self.assertEqual(fila['processados'], 2)
        self.assertEqual([x['origem'] for x in fila['ultimosLotesProcessados']], ['esp32', 'celular'])

    # ---------- mudança de contexto ----------
    def test_movimento_do_celular_suprime_alerta(self):
        token = self.token()
        for _ in range(5):                 # FC alta, MPU6050 em repouso, celular balançando
            self.assertEqual(self.movimento(token, 0.6).status_code, 200)
            # os 2 primeiros lotes ainda não enchem a janela (DADOS_INSUFICIENTES)
            self.assertNotEqual(self.lote_esp32(120)['estado'], 'ATENCAO')
        d = self.client.get(ESTADO, headers=self.cabecalho(token)).json()
        self.assertEqual(d['estado'], 'NORMAL')
        self.assertEqual(d['resumo']['movimento'], 'ACTIVE')
        self.assertEqual(d['resumo']['fonteMovimento'], 'celular')
        self.assertEqual(d['resumo']['movimentoEsp32'], 'REST')
        self.assertEqual(self.client.post(COMANDO, headers=self.cabecalho(token)).status_code, 409)

    def test_celular_parado_mantem_alerta_e_balancar_encerra(self):
        token = self.token()
        for _ in range(5):
            self.movimento(token, 0.02)                 # celular parado: sem contexto novo
            self.lote_esp32(120)
        self.assertEqual(self.client.get(ESTADO, headers=self.cabecalho(token)).json()['estado'], 'ATENCAO')
        self.relogio += 5                               # passa o tempo mínimo no estado
        r = self.movimento(token, 0.8)                  # paciente começou a se mexer
        self.assertEqual(r.json()['estado'], 'NORMAL')
        hist = self.client.get(ESTADO, headers=self.cabecalho(token)).json()['historico']
        self.assertEqual(hist[0]['razao'], 'movimento_no_celular')

    def test_contexto_do_celular_expira(self):
        token = self.token()
        self.movimento(token, 0.6)
        self.relogio += 10                              # celular parou de mandar dados
        for _ in range(5):
            self.lote_esp32(120)
        self.assertEqual(self.client.get(ESTADO, headers=self.cabecalho(token)).json()['estado'], 'ATENCAO')

    # ---------- ciclo 2 pelo app ----------
    def test_app_reconhece_alerta_com_token(self):
        token = self.token()
        for _ in range(5):
            self.lote_esp32(120)
        criado = self.client.post(COMANDO, headers=self.cabecalho(token))
        self.assertEqual(criado.status_code, 201)
        self.assertEqual(criado.json()['canal'], 'app')
        self.assertEqual(self.client.get(ESTADO, headers=self.cabecalho(token)).json()['comando']['status'],
                         'PENDENTE')


class TestarRegraContexto(unittest.TestCase):
    """A regra pura, sem HTTP: o contexto do celular vence o MPU6050 enquanto é recente."""

    def test_movimento_do_celular_sem_leituras_do_esp32_nao_muda_estado(self):
        m = Monitor()
        self.assertIsNone(m.registrar_movimento_app(0.9, 0))
        self.assertIsNone(m.estado)

    def test_contexto_vale_por_poucos_segundos(self):
        m = Monitor()
        m.registrar_movimento_app(0.9, 0)
        self.assertEqual(m.calcular(3)['fonteMovimento'], 'celular')
        self.assertEqual(m.calcular(30)['fonteMovimento'], 'esp32')


if __name__ == '__main__':
    unittest.main()
