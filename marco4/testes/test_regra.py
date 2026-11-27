"""Testes da regra (sem HTTP, sem Wokwi): python -m unittest discover -s marco4/testes -v"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from regra import Monitor, fc_valida, movimento  # noqa: E402


def alimentar(monitor, fc, de, ate, g=1.0):
    """Simula o ESP32: um lote de 3 leituras a cada 3 s, de 'de' até 'ate'."""
    for agora in range(de, ate + 1, 3):
        monitor.adicionar([{'fc': fc, 'g': g}] * 3, agora)


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
        alimentar(m, 80, 3, 6)                # 6 s de 10: cobertura 60%
        self.assertEqual(m.estado, 'DADOS_INSUFICIENTES')
        alimentar(m, 80, 9, 9)                # 9 s de 10: cobertura 90%
        self.assertEqual(m.estado, 'NORMAL')

    def test_fc_alta_em_repouso_precisa_persistir(self):
        m = Monitor()
        alimentar(m, 120, 3, 12)              # condição vista, mas ainda sem persistência/tempo mínimo
        self.assertEqual(m.estado, 'NORMAL')
        alimentar(m, 120, 15, 15)
        self.assertEqual(m.estado, 'ATENCAO')
        self.assertEqual(m.historico[-1]['razao'], 'condicao_persistiu')

    def test_histerese_na_saida(self):
        m = Monitor()
        alimentar(m, 120, 3, 15)
        alimentar(m, 95, 18, 27)              # abaixo de 100, mas acima de 92: continua
        self.assertEqual(m.estado, 'ATENCAO')
        alimentar(m, 80, 30, 30)              # média cai abaixo de 92
        self.assertEqual(m.estado, 'NORMAL')

    def test_movimento_ativo_nao_gera_alerta(self):
        m = Monitor()
        alimentar(m, 120, 3, 30, g=1.6)
        self.assertEqual(m.estado, 'NORMAL')

    def test_sensor_ausente(self):
        m = Monitor()
        alimentar(m, None, 3, 30)
        self.assertEqual(m.estado, 'DADOS_INSUFICIENTES')

    def test_silencio_vira_dados_insuficientes(self):
        m = Monitor()
        alimentar(m, 80, 3, 12)
        self.assertEqual(m.estado, 'NORMAL')
        m.verificar_silencio(25)              # 13 s sem nenhum lote
        self.assertEqual(m.estado, 'DADOS_INSUFICIENTES')
        self.assertEqual(m.historico[-1]['razao'], 'sem_leituras_recentes')


class TestarSilencioAdaptativo(unittest.TestCase):
    """O limite de silêncio acompanha o ritmo dos lotes (achado do ensaio no Wokwi)."""

    def test_ritmo_normal_mantem_8_s(self):
        m = Monitor()
        alimentar(m, 80, 3, 30)               # lote a cada 3 s: 2,5 x 3 = 7,5 -> piso de 8 s
        self.assertEqual(m.limite_silencio(), 8)

    def test_simulador_lento_nao_alterna_com_dados_insuficientes(self):
        # Wokwi a ~40% da velocidade: os lotes de 3 s chegam a cada 8 s de relógio.
        m = Monitor()
        for agora in range(8, 120, 8):
            m.verificar_silencio(agora - 1)   # o app consulta logo antes do próximo lote
            m.adicionar([{'fc': 135, 'g': 1.0}] * 3, agora)
        self.assertEqual(m.limite_silencio(), 20)
        self.assertEqual(m.estado, 'ATENCAO')
        razoes = [e['razao'] for e in m.historico]
        self.assertNotIn('sem_leituras_recentes', razoes[2:])   # depois de aprender o ritmo

    def test_falha_real_ainda_detectada_com_teto(self):
        m = Monitor()
        for agora in range(0, 200, 20):       # ritmo muito lento: 2,5 x 20 = 50 -> teto de 30 s
            m.adicionar([{'fc': 80, 'g': 1.0}] * 3, agora)
        self.assertEqual(m.limite_silencio(), 30)
        m.verificar_silencio(180 + 29)
        self.assertNotEqual(m.estado, 'DADOS_INSUFICIENTES')
        m.verificar_silencio(180 + 31)
        self.assertEqual(m.estado, 'DADOS_INSUFICIENTES')

    def test_uma_queda_isolada_nao_desloca_a_mediana(self):
        m = Monitor()
        alimentar(m, 80, 3, 15)
        m.adicionar([{'fc': 80, 'g': 1.0}] * 3, 40)   # 25 s de queda
        alimentar(m, 80, 43, 46)
        self.assertEqual(m.limite_silencio(), 8)

    def test_sem_nenhum_lote_nao_declara_silencio(self):
        m = Monitor()
        self.assertIsNone(m.verificar_silencio(100))
        self.assertIsNone(m.estado)


if __name__ == '__main__':
    unittest.main()
