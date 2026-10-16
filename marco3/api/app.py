"""Marco 3: API REST do Internet dos Coisos (protótipo acadêmico).

Só rotas, autenticação e autorização. A análise das leituras fica em regra.py.
Dados em memória: reiniciar o servidor apaga tudo.
Iniciar: python gerar_config.py (uma vez) e python app.py.

Ciclo 1: ESP32 --POST /api/leituras--> API (regra.py) --GET estado--> painel do cuidador
Ciclo 2: painel --POST comando--> API --GET comando--> ESP32 --POST ack--> API --> painel
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

from regra import Monitor

BASE = Path(__file__).resolve().parent
ONLINE_S = 10          # sem contato do ESP32 por 10 s: "sem contato recente"
MAX_LEITURAS = 10      # o ESP32 manda 3 por lote; folga para atrasos


def carregar_env_local():
    """Lê o .env local, sem biblioteca extra; não sobrescreve variáveis reais."""
    arquivo = BASE / '.env'
    if arquivo.is_file():
        for linha in arquivo.read_text(encoding='utf-8').splitlines():
            linha = linha.strip()
            if linha and not linha.startswith('#') and '=' in linha:
                nome, valor = linha.split('=', 1)
                os.environ.setdefault(nome.strip(), valor.strip())


def conferir_senha(senha: str, senha_hash: str) -> bool:
    """Calcula o scrypt da senha digitada com o mesmo salt e compara com o hash salvo."""
    try:
        algoritmo, salt_hex, hash_hex = senha_hash.split('$')
        if algoritmo != 'scrypt':
            return False
        calculado = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(salt_hex),
                                   n=2**14, r=8, p=1)
        return hmac.compare_digest(calculado, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


def agora_utc():
    return datetime.now(timezone.utc).isoformat()


def create_app():
    carregar_env_local()
    secret = os.getenv('APP_SECRET_KEY', '')
    chave = os.getenv('DEVICE_API_KEY', '')
    senha_hash = os.getenv('CUIDADOR_SENHA_HASH', '')
    if len(secret) < 32 or len(chave) < 24 or not senha_hash:
        raise RuntimeError('Execute primeiro: python gerar_config.py em marco3/api')

    # Vínculos de autorização: este ESP32 publica por este paciente,
    # e só este cuidador pode ver o paciente e mandar comando.
    device_id = os.getenv('DEVICE_ID', 'esp32-borda-01')
    patient_id = os.getenv('PATIENT_ID', 'patient-0042')
    cuidador = os.getenv('CUIDADOR_USUARIO', 'cuidador01')

    app = FastAPI(title='Internet dos Coisos | Marco 3', version='3.1')
    # Cookie assinado com APP_SECRET_KEY. SameSite=Lax: o navegador não envia o
    # cookie em POST vindo de outro site (por isso não usamos token CSRF).
    app.add_middleware(SessionMiddleware, secret_key=secret,
                       session_cookie='coisos_session', max_age=1800,
                       same_site='lax', https_only=os.getenv('COOKIE_SECURE', '0') == '1')
    templates = Jinja2Templates(directory=str(BASE / 'templates'))

    # Rotas async rodam uma por vez no mesmo laço de eventos: sem await no meio
    # das alterações, não é preciso Lock.
    monitor = Monitor()
    dados = {
        'lotes_vistos': deque(maxlen=100),   # loteId recentes, para ignorar repetidos
        'lotes': 0,
        'contato_em': None,
        'hora_contato': None,
        'comando': None,                     # um comando por vez (ciclo 2)
    }

    # ---------------- autenticação e autorização ----------------
    def cuidador_logado(request):
        """Autenticação do cuidador: a sessão diz quem fez login."""
        return request.session.get('usuario') == cuidador

    def dispositivo_autenticado(request):
        """Autenticação do ESP32: chave enviada no cabeçalho X-Device-Key."""
        token = request.headers.get('X-Device-Key', '')
        return bool(token) and hmac.compare_digest(token, chave)

    def dispositivo_autorizado(corpo):
        """Autorização do ESP32: este dispositivo pode publicar por este paciente?"""
        return (isinstance(corpo, dict) and corpo.get('deviceId') == device_id
                and corpo.get('entityId') == patient_id)

    def registrar_contato():
        dados['contato_em'] = time.monotonic()
        dados['hora_contato'] = agora_utc()

    async def ler_json(request):
        try:
            valor = json.loads(await request.body())
            return valor if isinstance(valor, dict) else None
        except (UnicodeDecodeError, ValueError):
            return None

    # ---------------- login do cuidador ----------------
    @app.get('/', include_in_schema=False)
    async def inicio(request: Request):
        return RedirectResponse('/painel' if cuidador_logado(request) else '/login', 303)

    @app.get('/login', response_class=HTMLResponse, include_in_schema=False)
    async def login_form(request: Request):
        if cuidador_logado(request):
            return RedirectResponse('/painel', 303)
        return templates.TemplateResponse(request, 'login.html', {'erro': None})

    @app.post('/login', response_class=HTMLResponse, include_in_schema=False)
    async def login(request: Request):
        form = parse_qs((await request.body()).decode('utf-8', 'ignore'))
        usuario = form.get('usuario', [''])[0]
        senha = form.get('senha', [''])[0]
        if usuario == cuidador and conferir_senha(senha, senha_hash):
            request.session.clear()
            request.session['usuario'] = cuidador
            request.session['paciente'] = patient_id
            return RedirectResponse('/painel', 303)
        return templates.TemplateResponse(request, 'login.html',
                                          {'erro': 'Usuario ou senha incorretos.'}, status_code=401)

    @app.post('/logout', include_in_schema=False)
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse('/login', 303)

    @app.get('/painel', response_class=HTMLResponse, include_in_schema=False)
    async def painel(request: Request):
        if not cuidador_logado(request):
            return RedirectResponse('/login', 303)
        return templates.TemplateResponse(request, 'painel.html',
                                          {'usuario': cuidador, 'paciente': patient_id})

    # ---------------- ciclo 1: leituras do ESP32 ----------------
    @app.post('/api/leituras', tags=['Dispositivo'])
    async def receber_leituras(request: Request):
        if not dispositivo_autenticado(request):
            return JSONResponse({'erro': 'Chave do dispositivo invalida'}, 401)
        corpo = await ler_json(request)
        if corpo is None:
            return JSONResponse({'erro': 'Envie um objeto JSON'}, 400)
        if not dispositivo_autorizado(corpo):
            return JSONResponse({'erro': 'Dispositivo/paciente nao autorizado'}, 403)
        lote_id, leituras = corpo.get('loteId'), corpo.get('leituras')
        if (not isinstance(lote_id, str) or not lote_id or not isinstance(leituras, list)
                or not 1 <= len(leituras) <= MAX_LEITURAS
                or not all(isinstance(l, dict) for l in leituras)):
            return JSONResponse({'erro': 'Esperado loteId e leituras [{fc, g}]'}, 400)

        registrar_contato()
        if lote_id in dados['lotes_vistos']:     # o ESP32 reenviou o mesmo lote
            return {'status': 'duplicado', 'estado': monitor.estado}
        dados['lotes_vistos'].append(lote_id)
        dados['lotes'] += 1
        transicao = monitor.adicionar(leituras, time.monotonic())
        if transicao:
            transicao['horaUtc'] = agora_utc()
        return {'status': 'recebido', 'estado': monitor.estado}

    @app.get('/api/pacientes/{codigo}/estado', tags=['Cuidador'])
    async def estado(request: Request, codigo: str):
        if not cuidador_logado(request):
            return JSONResponse({'erro': 'Faca login'}, 401)
        if request.session.get('paciente') != codigo:
            return JSONResponse({'erro': 'Sem permissao para este paciente'}, 403)
        transicao = monitor.verificar_silencio(time.monotonic())
        if transicao:
            transicao['horaUtc'] = agora_utc()
        online = dados['contato_em'] is not None and time.monotonic() - dados['contato_em'] < ONLINE_S
        return {
            'paciente': codigo,
            'dispositivo': device_id,
            'online': online,
            'ultimoContatoUtc': dados['hora_contato'],
            'estado': monitor.estado or 'SEM_DADOS',
            'resumo': monitor.resumo,
            'historico': list(reversed(monitor.historico)),
            'lotesRecebidos': dados['lotes'],
            'comando': dados['comando'],
        }

    # ---------------- ciclo 2: comando do cuidador e ack do ESP32 ----------------
    @app.post('/api/pacientes/{codigo}/comando', tags=['Cuidador'])
    async def criar_comando(request: Request, codigo: str):
        if not cuidador_logado(request):
            return JSONResponse({'erro': 'Faca login'}, 401)
        if request.session.get('paciente') != codigo:
            return JSONResponse({'erro': 'Sem permissao para este paciente'}, 403)
        if monitor.estado != 'ATENCAO':
            return JSONResponse({'erro': 'Nao ha alerta ativo para reconhecer'}, 409)
        c = dados['comando']
        if c and c['status'] != 'EXECUTADO':     # clique repetido: devolve o mesmo comando
            return JSONResponse(c, 200)
        dados['comando'] = {
            'commandId': 'cmd-' + secrets.token_hex(4), 'tipo': 'RECONHECER_ALERTA',
            'emitidoPor': cuidador, 'status': 'PENDENTE',
            'criadoEmUtc': agora_utc(), 'confirmadoEmUtc': None,
        }
        return JSONResponse(dados['comando'], 201)

    @app.get('/api/dispositivo/comando', tags=['Dispositivo'])
    async def entregar_comando(request: Request, deviceId: str = '', entityId: str = ''):
        if not dispositivo_autenticado(request):
            return JSONResponse({'erro': 'Chave do dispositivo invalida'}, 401)
        if not dispositivo_autorizado({'deviceId': deviceId, 'entityId': entityId}):
            return JSONResponse({'erro': 'Dispositivo/paciente nao autorizado'}, 403)
        registrar_contato()                      # a consulta também prova que o ESP32 está vivo
        c = dados['comando']
        if not c or c['status'] == 'EXECUTADO':
            return {}
        c['status'] = 'ENTREGUE'                 # entrega de novo até chegar o ack
        return {'commandId': c['commandId'], 'tipo': c['tipo']}

    @app.post('/api/dispositivo/comando/ack', tags=['Dispositivo'])
    async def confirmar_comando(request: Request):
        if not dispositivo_autenticado(request):
            return JSONResponse({'erro': 'Chave do dispositivo invalida'}, 401)
        corpo = await ler_json(request)
        if not dispositivo_autorizado(corpo):
            return JSONResponse({'erro': 'Dispositivo/paciente nao autorizado'}, 403)
        c = dados['comando']
        if not c or corpo.get('commandId') != c['commandId']:
            return JSONResponse({'erro': 'Comando desconhecido'}, 404)
        if c['status'] == 'PENDENTE':
            return JSONResponse({'erro': 'Comando ainda nao foi entregue'}, 409)
        if c['status'] == 'ENTREGUE':
            c['status'] = 'EXECUTADO'
            c['confirmadoEmUtc'] = agora_utc()
        return {'status': c['status']}

    return app


if __name__ == '__main__':
    print('Marco 3: abra http://127.0.0.1:5000/login')
    uvicorn.run(create_app(), host='127.0.0.1', port=5000)
