"""Envia leituras DIDÁTICAS assinadas à API para testar sem Wokwi.

Na raiz: py marco3/scripts/simular_sem_wokwi.py
Requer a API rodando e api/.env gerado. Não é substituto para testar o ESP32.
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'api'))
from app import carregar_env_local  # noqa: E402


def enviar(url_base, chave, dispositivo, paciente, lote_id, fc, g):
    rota = '/api/leituras'
    corpo = json.dumps({
        'deviceId': dispositivo,
        'entityId': paciente,
        'loteId': lote_id,
        'leituras': [{'fc': fc, 'g': g} for _ in range(3)],
    }, separators=(',', ':')).encode()
    timestamp = str(int(time.time()))
    mensagem = f'{timestamp}\nPOST {rota}\n'.encode() + corpo
    assinatura = hmac.new(chave.encode(), mensagem, hashlib.sha256).hexdigest()
    req = Request(url_base.rstrip('/') + rota, data=corpo, method='POST', headers={
        'Content-Type': 'application/json', 'X-Timestamp': timestamp,
        'X-Assinatura': assinatura,
    })
    try:
        with urlopen(req, timeout=15) as resposta:
            return resposta.status, json.loads(resposta.read())
    except HTTPError as exc:
        return exc.code, {'erro': exc.read().decode('utf-8', 'replace')[:300]}


def main():
    parser = argparse.ArgumentParser(description='Simulação software assinada para validar API/fila/banco/painel')
    parser.add_argument('--url', default='http://127.0.0.1:5000')
    parser.add_argument('--intervalo', type=float, default=3.0,
                        help='Segundos entre lotes (padrão: 3; como o Wokwi)')
    args = parser.parse_args()
    carregar_env_local()
    chave = os.getenv('DEVICE_API_KEY', '')
    if not chave:
        print('[ERRO] Gere marco3/api/.env com gerar_config.py')
        return 1
    dispositivo = os.getenv('DEVICE_ID', 'esp32-borda-01')
    paciente = os.getenv('PATIENT_ID', 'patient-0042')
    execucao = uuid.uuid4().hex[:8]
    # >= 3 lotes normais: janela de 10 leituras atinge cobertura; 4 elevados: alerta.
    roteiros = ([('NORMAL', 80, 1.0)] * 4 +
                [('ALERTA', 135, 1.0)] * 5 +
                [('MOVIMENTO', 135, 1.75)] * 3 +
                [('SENSOR_AUSENTE', None, 1.0)] * 4 +
                [('RECUPERACAO', 80, 1.0)] * 4)
    print('Teste SEM hardware virtual: ESP32 não está sendo executado!')
    print('Acompanhe o painel autenticado em http://127.0.0.1:5000/login')
    try:
        for n, (cenario, fc, g) in enumerate(roteiros, 1):
            codigo, resposta = enviar(args.url, chave, dispositivo, paciente,
                                     f'demo-{execucao}-{n:02}', fc, g)
            print(f'{n:02} {cenario:<15} HTTP {codigo} estado={resposta.get("estado", "—")} '
                  f'{resposta.get("erro", "")}')
            if codigo != 200:
                return 2
            if n != len(roteiros):
                time.sleep(max(0, args.intervalo))
        print('[OK] Fluxo API + fila exercitado. Confira WebSocket e TimescaleDB separadamente.')
        return 0
    except (URLError, TimeoutError, ValueError) as exc:
        print('[ERRO] Falha de comunicação com a API:', type(exc).__name__)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
