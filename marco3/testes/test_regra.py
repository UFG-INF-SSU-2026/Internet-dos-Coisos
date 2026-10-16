"""Testes da regra (sem HTTP, sem Wokwi): python -m unittest discover -s marco3/testes -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from regra import Monitor, fc_valida, movimento  # noqa: E402


def alimentar(monitor, fc, de, ate, g=1.0):
    """Simula o ESP32: um lote de 5 leituras a cada 5 s, de 'de' até 'ate'."""
    for agora in range(de, ate + 1, 5):
        monitor.adicionar([{'fc': fc, 'g': g}] * 5, agora)


class TestarRegra(unittest.TestCase):
    def test_classificacao_das_leituras(self):
        self.assertEqual(fc_valida(80), 80.0)
        self.assertIsNone(fc_valida(250))     # fora de faixa
        self.assertIsNone(fc_valida(None))    # sensor ausente
        self.assertIsNone(fc_valida(True))
        self.assertEqual(movimento(1.05), 'REST')
        self.assertEqual(movimento(1.6), 'ACTIVE')
        self.assertEqual(movimento(None), 'INVALIDO')

    def test_poucos_dados_e_depois_normal(self):
        m = Monitor()
        alimentar(m, 80, 5, 10)               # 10 s de 20: cobertura 50%
        self.assertEqual(m.estado, 'DADOS_INSUFICIENTES')
        alimentar(m, 80, 15, 15)              # 15 s de 20: cobertura 75%
        self.assertEqual(m.estado, 'NORMAL')

    def test_fc_alta_em_repouso_precisa_persistir(self):
        m = Monitor()
        alimentar(m, 120, 5, 20)              # condição vista, mas ainda sem persistência/tempo mínimo
        self.assertEqual(m.estado, 'NORMAL')
        alimentar(m, 120, 25, 25)
        self.assertEqual(m.estado, 'ATENCAO')
        self.assertEqual(m.historico[-1]['razao'], 'condicao_persistiu')

    def test_histerese_na_saida(self):
        m = Monitor()
        alimentar(m, 120, 5, 25)
        alimentar(m, 95, 30, 45)              # abaixo de 100, mas acima de 92: continua
        self.assertEqual(m.estado, 'ATENCAO')
        alimentar(m, 80, 50, 50)              # média cai abaixo de 92
        self.assertEqual(m.estado, 'NORMAL')

    def test_movimento_ativo_nao_gera_alerta(self):
        m = Monitor()
        alimentar(m, 120, 5, 40, g=1.6)
        self.assertEqual(m.estado, 'NORMAL')

    def test_sensor_ausente(self):
        m = Monitor()
        alimentar(m, None, 5, 30)
        self.assertEqual(m.estado, 'DADOS_INSUFICIENTES')

    def test_silencio_vira_dados_insuficientes(self):
        m = Monitor()
        alimentar(m, 80, 5, 20)
        self.assertEqual(m.estado, 'NORMAL')
        m.verificar_silencio(40)              # 20 s sem nenhum lote
        self.assertEqual(m.estado, 'DADOS_INSUFICIENTES')
        self.assertEqual(m.historico[-1]['razao'], 'sem_leituras_recentes')


if __name__ == '__main__':
    unittest.main()
