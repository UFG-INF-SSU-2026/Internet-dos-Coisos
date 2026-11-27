"""Avaliação reprodutível do Marco 4 (números usados no artigo).

Na raiz:  .\\.venv\\Scripts\\python.exe marco4\\scripts\\avaliar.py
Não precisa de Wokwi, banco nem rede: a API roda no próprio processo
(TestClient) e a regra é exercitada com relógio simulado.

Mede:
  1. latência de processamento na API (HMAC/token + fila FIFO + regra);
  2. custo do login do app (scrypt);
  3. tempos de decisão da regra em segundos simulados;
  4. efeito da mudança de contexto (alertas com e sem o celular);
  5. descarte de leituras do celular com atrasos sintéticos.
"""
import hashlib
import hmac
import json
import os
import random
import secrets
import statistics
import sys
import time
from pathlib import Path
from unittest.mock import patch

API = Path(__file__).resolve().parents[1] / 'api'
sys.path.insert(0, str(API))

from fastapi.testclient import TestClient  # noqa: E402

import app as modulo_app  # noqa: E402
from regra import Monitor  # noqa: E402

CHAVE = 'chave-de-avaliacao-com-mais-de-24-caracteres'
SENHA = 'senha-de-avaliacao'
N = 300


def criar_cliente():
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(SENHA.encode(), salt=sal, n=2**14, r=8, p=1)
    env = {'APP_SECRET_KEY': 'segredo-de-avaliacao-com-mais-de-32-caracteres!!',
           'DEVICE_API_KEY': CHAVE, 'CUIDADOR_USUARIO': 'cuidador01',
           'CUIDADOR_SENHA_HASH': f'scrypt${sal.hex()}${derivada.hex()}',
           'DEVICE_ID': 'esp32-borda-01', 'PATIENT_ID': 'patient-0042', 'DATABASE_URL': ''}
    with patch.dict(os.environ, env):
        return TestClient(modulo_app.create_app())


def assinar(rota, corpo):
    ts = str(int(time.time()))
    msg = f'{ts}\nPOST {rota}\n'.encode() + corpo
    return {'X-Timestamp': ts, 'X-Assinatura': hmac.new(CHAVE.encode(), msg, hashlib.sha256).hexdigest(),
            'Content-Type': 'application/json'}


def resumo_ms(amostras):
    ordenadas = sorted(amostras)
    p95 = ordenadas[int(0.95 * (len(ordenadas) - 1))]
    return (f'media {statistics.mean(amostras):.2f} ms | mediana {statistics.median(amostras):.2f} ms'
            f' | p95 {p95:.2f} ms | n={len(amostras)}')


def medir_latencias():
    cliente = criar_cliente()
    lotes = []
    for i in range(N):
        corpo = json.dumps({'deviceId': 'esp32-borda-01', 'entityId': 'patient-0042',
                            'loteId': f'aval-{i}', 'leituras': [{'fc': 80, 'g': 1.0}] * 3}).encode()
        inicio = time.perf_counter()
        r = cliente.post('/api/leituras', content=corpo, headers=assinar('/api/leituras', corpo))
        lotes.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200, r.text

    logins = []
    for _ in range(20):
        inicio = time.perf_counter()
        r = cliente.post('/api/app/login', json={'usuario': 'cuidador01', 'senha': SENHA})
        logins.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200
    token = r.json()['token']

    moves = []
    base = int(time.time() * 1000)
    for i in range(N):
        inicio = time.perf_counter()
        r = cliente.post('/api/app/leituras', headers={'Authorization': f'Bearer {token}'},
                         json={'entityId': 'patient-0042', 'intensidade': 0.3, 'capturadoEmMs': base + i})
        moves.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200, r.text

    estados = []
    for _ in range(N):
        inicio = time.perf_counter()
        cliente.get('/api/pacientes/patient-0042/estado', headers={'Authorization': f'Bearer {token}'})
        estados.append((time.perf_counter() - inicio) * 1000)
    cliente.close()
    return {'lote ESP32 (HMAC + fila + regra)': resumo_ms(lotes),
            'leitura do app (token + fila + regra)': resumo_ms(moves),
            'consulta de estado pelo app (token)': resumo_ms(estados),
            'login do app (scrypt n=2^14)': resumo_ms(logins)}


# ---------------- regra com relógio simulado ----------------
LOTE_S, APP_S = 3, 2


def simular(duracao_s, fc_em, celular_ativo_em=lambda t: None, inicio_fc_alta=None):
    """Lote de 3 leituras a cada 3 s; leitura do celular a cada 2 s. Devolve as transições."""
    m, eventos = Monitor(), []
    for t in range(0, duracao_s + 1):
        if t % APP_S == 0:
            intensidade = celular_ativo_em(t)
            if intensidade is not None:
                ev = m.registrar_movimento_app(intensidade, t)
                if ev:
                    eventos.append((t, ev['estado'], ev['razao']))
        if t % LOTE_S == 0 and t > 0:
            ev = m.adicionar([{'fc': fc_em(t - k), 'g': 1.0} for k in (2, 1, 0)], t)
            if ev:
                eventos.append((t, ev['estado'], ev['razao']))
    return eventos


def primeira(eventos, estado, depois=0):
    return next((t for t, e, _ in eventos if e == estado and t >= depois), None)


def medir_regra():
    r = {}
    # FC normal por 30 s e depois 120 bpm em repouso.
    ev = simular(120, lambda t: 80 if t < 30 else 120)
    t_atencao = primeira(ev, 'ATENCAO', 30)
    r['tempo ate NORMAL a partir do inicio (janela cheia)'] = f'{primeira(ev, "NORMAL")} s'
    r['tempo ate ATENCAO depois que a FC sobe para 120 bpm'] = f'{t_atencao - 30} s'
    # Saída com histerese: 120 -> 95 (entre 92 e 100) -> 85.
    ev = simular(150, lambda t: 120 if t < 60 else (95 if t < 100 else 85))
    saida95 = [x for x in ev if 60 <= x[0] < 100 and x[1] == 'NORMAL']
    r['FC em 95 bpm (entre 92 e 100) encerra o alerta?'] = 'nao (histerese)' if not saida95 else 'sim'
    r['tempo ate NORMAL depois que a FC cai para 85 bpm'] = f'{primeira(ev, "NORMAL", 100) - 100} s'

    # Mudança de contexto em 10 minutos de FC 120 bpm.
    sem = simular(600, lambda t: 120)
    com = simular(600, lambda t: 120, celular_ativo_em=lambda t: 0.6)
    r['alertas em 10 min de FC 120 sem celular'] = str(sum(1 for _, e, _ in sem if e == 'ATENCAO'))
    r['alertas em 10 min de FC 120 com celular em movimento'] = str(sum(1 for _, e, _ in com if e == 'ATENCAO'))
    # Celular começa a balançar com o alerta ativo; depois para.
    ev = simular(200, lambda t: 120, celular_ativo_em=lambda t: 0.6 if 60 <= t < 120 else 0.02)
    t_fim = primeira(ev, 'NORMAL', 60)
    razao = next(z for t, e, z in ev if t == t_fim and e == 'NORMAL')
    r['alerta ativo: tempo ate NORMAL depois de balancar o celular'] = f'{t_fim - 60} s ({razao})'
    r['celular fica parado (envia repouso): tempo ate o alerta voltar'] = \
        f'{primeira(ev, "ATENCAO", 120) - 120} s'
    ev = simular(200, lambda t: 120, celular_ativo_em=lambda t: 0.6 if 60 <= t < 120 else None)
    r['celular para de enviar: tempo ate o alerta voltar'] = f'{primeira(ev, "ATENCAO", 120) - 120} s'
    return r


def medir_descartes(semente=42, n=2000):
    """Atraso de rede sintético (exponencial, média 2 s) + 5% de leituras retidas 12-30 s."""
    rnd = random.Random(semente)
    ultima, aceitas, motivos = None, 0, {'atrasada': 0, 'fora_de_ordem': 0}
    eventos = []
    for i in range(n):
        captura = i * 2000
        atraso = rnd.expovariate(1 / 2000)
        if rnd.random() < 0.05:
            atraso = rnd.uniform(12000, 30000)
        eventos.append((captura + atraso, captura))
    for chegada, captura in sorted(eventos):
        if chegada - captura > 10_000:
            motivos['atrasada'] += 1
        elif ultima is not None and captura <= ultima:
            motivos['fora_de_ordem'] += 1
        else:
            aceitas += 1
            ultima = captura
    return {'leituras sinteticas': str(n), 'aceitas': f'{aceitas} ({100 * aceitas / n:.1f}%)',
            'descartadas por atraso > 10 s': str(motivos['atrasada']),
            'descartadas fora de ordem': str(motivos['fora_de_ordem'])}


if __name__ == '__main__':
    print(f'# Avaliacao Marco 4 | Python {sys.version.split()[0]} | {sys.platform}')
    for titulo, bloco in [('Latencia na API (em processo, sem rede)', medir_latencias()),
                          ('Regra com relogio simulado (lote a cada 3 s, celular a cada 2 s)', medir_regra()),
                          ('Validade das leituras do celular (semente 42)', medir_descartes())]:
        print(f'\n## {titulo}')
        for nome, valor in bloco.items():
            print(f'- {nome}: {valor}')
