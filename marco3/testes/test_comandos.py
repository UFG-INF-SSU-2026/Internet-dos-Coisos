"""Ciclo 2 (comando do cuidador -> ESP32 -> ack): python -m unittest discover -s marco3/testes -v"""
import json
import re
import unittest

import test_api  # reaproveita setUp/helpers sem reexecutar os testes do ciclo 1


class TestarCiclo2(unittest.TestCase):
    setUp = test_api.TestarMarco3.setUp
    tearDown = test_api.TestarMarco3.tearDown
    evento = test_api.TestarMarco3.evento
    csrf = test_api.TestarMarco3.csrf
    entrar = test_api.TestarMarco3.entrar

    def preparar_alerta(self):
        r = self.client.post('/api/eventos', json=self.evento(1, estado='ATENCAO'), headers=self.headers)
        self.assertEqual(r.status_code, 201)
        self.entrar()
        self.token = self.csrf('/painel')

    def cmd(self, token=None, corpo=None, codigo='patient-0042'):
        h = {'X-CSRF-Token': self.token if token is None else token}
        return self.client.post(f'/api/pacientes/{codigo}/comandos', headers=h,
                                json=corpo or {'tipo': 'RECONHECER_ALERTA'})

    def dev(self, **extra):
        return {'deviceId': 'esp32-borda-01', 'entityId': 'patient-0042', **extra}

    def test_ciclo_completo(self):
        self.preparar_alerta()
        r = self.cmd(); self.assertEqual(r.status_code, 201)
        cid = r.json()['commandId']
        r = self.client.get('/api/dispositivo/comandos', params=self.dev(), headers=self.headers)
        self.assertEqual(r.json()['comandos'], [{'commandId': cid, 'tipo': 'RECONHECER_ALERTA'}])
        r = self.client.post(f'/api/comandos/{cid}/ack', headers=self.headers,
                             json=self.dev(commandId=cid, resultado='EXECUTADO'))
        self.assertEqual(r.status_code, 201)
        estado = self.client.get('/api/pacientes/patient-0042/estado').json()
        self.assertEqual(estado['ultimoComando']['status'], 'EXECUTADO')
        self.assertEqual(estado['estado'], 'ATENCAO')   # reconhecer nao muda o estado clinico
        # ack repetido e idempotente; comando nao e mais entregue
        r = self.client.post(f'/api/comandos/{cid}/ack', headers=self.headers,
                             json=self.dev(commandId=cid, resultado='EXECUTADO'))
        self.assertEqual(r.status_code, 200)
        r = self.client.get('/api/dispositivo/comandos', params=self.dev(), headers=self.headers)
        self.assertEqual(r.json()['comandos'], [])

    def test_comando_exige_login_csrf_e_paciente(self):
        self.client.post('/api/eventos', json=self.evento(1, estado='ATENCAO'), headers=self.headers)
        r = self.client.post('/api/pacientes/patient-0042/comandos', json={'tipo': 'RECONHECER_ALERTA'})
        self.assertEqual(r.status_code, 401)
        self.entrar(); self.token = self.csrf('/painel')
        self.assertEqual(self.cmd(token='errado').status_code, 403)
        self.assertEqual(self.cmd(codigo='patient-9999').status_code, 403)

    def test_tipo_invalido_e_sem_alerta(self):
        self.entrar(); self.token = self.csrf('/painel')
        self.assertEqual(self.cmd().status_code, 409)               # sem evento/alerta
        self.preparar_alerta()
        self.assertEqual(self.cmd(corpo={'tipo': 'DESLIGAR_TUDO'}).status_code, 400)

    def test_clique_repetido_nao_duplica(self):
        self.preparar_alerta()
        a = self.cmd(); b = self.cmd()
        self.assertEqual((a.status_code, b.status_code), (201, 200))
        self.assertEqual(a.json()['commandId'], b.json()['commandId'])

    def test_dispositivo_so_com_chave_e_vinculo(self):
        self.preparar_alerta(); cid = self.cmd().json()['commandId']
        self.assertEqual(self.client.get('/api/dispositivo/comandos', params=self.dev()).status_code, 401)
        self.assertEqual(self.client.get('/api/dispositivo/comandos', headers=self.headers,
                                         params={'deviceId': 'outro', 'entityId': 'patient-0042'}).status_code, 403)
        # cuidador (sessao) nao pode forjar ack: falta a chave do dispositivo
        r = self.client.post(f'/api/comandos/{cid}/ack', json=self.dev(commandId=cid, resultado='EXECUTADO'))
        self.assertEqual(r.status_code, 401)

    def test_ack_antes_da_entrega_e_desconhecido(self):
        self.preparar_alerta(); cid = self.cmd().json()['commandId']
        r = self.client.post(f'/api/comandos/{cid}/ack', headers=self.headers,
                             json=self.dev(commandId=cid, resultado='EXECUTADO'))
        self.assertEqual(r.status_code, 409)                        # ainda PENDENTE
        r = self.client.post('/api/comandos/cmd-x/ack', headers=self.headers,
                             json=self.dev(commandId='cmd-x', resultado='EXECUTADO'))
        self.assertEqual(r.status_code, 404)


if __name__ == '__main__':
    unittest.main()
