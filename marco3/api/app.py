"""Marco 3: uma API REST HTTP + login do cuidador (protótipo acadêmico).

Sem Neon: os eventos ficam na memória e são perdidos ao reiniciar o servidor.
Iniciar: python gerar_config.py (uma vez) e python app.py.
"""

import hashlib
import hmac
import os
import secrets
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

BASE = Path(__file__).resolve().parent
ESTADOS = {'NORMAL', 'ATENCAO', 'DADOS_INSUFICIENTES'}
MOVIMENTOS = {'REST', 'ACTIVE', 'INVALIDO'}
# Marco 3 (ciclo 2): o cuidador PRODUZ comandos; o ESP32 os CONSOME e PRODUZ o ack.
TIPOS_COMANDO = {'RECONHECER_ALERTA'}
RESULTADOS_ACK = {'EXECUTADO', 'IGNORADO'}
TTL_COMANDO_S = 120
CAMPOS = {'schemaVersion', 'eventType', 'eventId', 'deviceId', 'entityId',
          'bootId', 'eventTimeMs', 'sequence', 'value', 'unit', 'state',
          'motion', 'coverageFc', 'coverageMov', 'reason'}


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
    """Compara senha com hash scrypt gravado na configuração local."""
    try:
        algoritmo, salt_hex, hash_hex = senha_hash.split('$')
        if algoritmo != 'scrypt':
            return False
        calculado = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(salt_hex),
                                   n=2**14, r=8, p=1)
        return hmac.compare_digest(calculado, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


def create_app():
    carregar_env_local()
    secret = os.getenv('APP_SECRET_KEY', '')
    chave = os.getenv('DEVICE_API_KEY', '')
    senha_hash = os.getenv('CUIDADOR_SENHA_HASH', '')
    if len(secret) < 32 or len(chave) < 24 or not senha_hash:
        raise RuntimeError('Execute primeiro: python gerar_config.py em marco3/api')

    device_id = os.getenv('DEVICE_ID', 'esp32-borda-01')
    patient_id = os.getenv('PATIENT_ID', 'patient-0042')
    cuidador = os.getenv('CUIDADOR_USUARIO', 'cuidador01')
    app = FastAPI(title='Internet dos Coisos | Marco 3', version='3.0',
                  description='API REST de demonstração para Sistemas Ubíquos (UFG).')
    app.add_middleware(SessionMiddleware, secret_key=secret,
                       session_cookie='coisos_session', max_age=1800,
                       same_site='lax', https_only=os.getenv('COOKIE_SECURE', '0') == '1')
    templates = Jinja2Templates(directory=str(BASE / 'templates'))
    lock = Lock()
    dados = {
        'evento': None,
        'boot_id': None,
        'boots_vistos': set(),
        'ultima_seq': 0,
        'contato_em': None,
        'hora_contato': None,
        'recebidos': 0,
        'duplicados': 0,
        'saltos': 0,
        'ids_recentes': OrderedDict(),
        'comandos': OrderedDict(),   # commandId -> dict
    }

    @app.middleware('http')
    async def cabecalhos(request: Request, call_next):
        resposta = await call_next(request)
        resposta.headers['X-Content-Type-Options'] = 'nosniff'
        resposta.headers['X-Frame-Options'] = 'DENY'
        if request.url.path in ('/', '/login', '/painel') or request.url.path.startswith('/api/'):
            resposta.headers['Cache-Control'] = 'no-store'
        return resposta

    def csrf(request):
        if 'csrf' not in request.session:
            request.session['csrf'] = secrets.token_urlsafe(20)
        return request.session['csrf']

    def conferir_csrf(request, form):
        esperado = request.session.get('csrf', '')
        recebido = form.get('csrf', '')
        return bool(esperado and recebido and hmac.compare_digest(esperado, recebido))

    def autenticado(request):
        return request.session.get('usuario') == cuidador

    def chave_valida(request):
        token = request.headers.get('X-Device-Key', '')
        return bool(token and hmac.compare_digest(token, chave))

    def vinculo_valido(corpo):
        return isinstance(corpo, dict) and (corpo.get('deviceId') == device_id
                                             and corpo.get('entityId') == patient_id)

    async def corpo_json(request):
        conteudo = await request.body()
        if len(conteudo) > 4096:
            return None
        try:
            import json
            valor = json.loads(conteudo)
            return valor if isinstance(valor, dict) else None
        except (UnicodeDecodeError, ValueError):
            return None

    async def form_data(request):
        conteudo = await request.body()
        if len(conteudo) > 4096:
            return {}
        try:
            dados_form = parse_qs(conteudo.decode('utf-8'), max_num_fields=10)
            return {campo: valores[0] for campo, valores in dados_form.items() if valores}
        except (UnicodeDecodeError, ValueError):
            return {}

    @app.get('/', include_in_schema=False)
    async def inicio(request: Request):
        return RedirectResponse('/painel' if autenticado(request) else '/login', 303)

    @app.get('/login', response_class=HTMLResponse, include_in_schema=False)
    async def login_form(request: Request):
        if autenticado(request):
            return RedirectResponse('/painel', 303)
        return templates.TemplateResponse(request, 'login.html',
                                          {'erro': None, 'csrf': csrf(request)})

    @app.post('/login', response_class=HTMLResponse, include_in_schema=False)
    async def login(request: Request):
        form = await form_data(request)
        if not conferir_csrf(request, form):
            return HTMLResponse('Formulario expirado. Atualize /login.', 400)
        usuario = form.get('usuario', '')
        senha = form.get('senha', '')
        if usuario.isascii() and hmac.compare_digest(usuario, cuidador) and conferir_senha(senha, senha_hash):
            request.session.clear()
            request.session['usuario'] = cuidador
            request.session['paciente'] = patient_id
            return RedirectResponse('/painel', 303)
        return templates.TemplateResponse(request, 'login.html',
                                          {'erro': 'Usuario ou senha incorretos.',
                                           'csrf': csrf(request)}, status_code=401)

    @app.post('/logout', include_in_schema=False)
    async def logout(request: Request):
        form = await form_data(request)
        if not conferir_csrf(request, form):
            return HTMLResponse('Formulario invalido.', 400)
        request.session.clear()
        return RedirectResponse('/login', 303)

    @app.get('/painel', response_class=HTMLResponse, include_in_schema=False)
    async def painel(request: Request):
        if not autenticado(request):
            return RedirectResponse('/login', 303)
        return templates.TemplateResponse(request, 'painel.html',
                                          {'usuario': cuidador, 'paciente': patient_id,
                                           'csrf': csrf(request)})

    @app.post('/api/heartbeat', tags=['Dispositivo'])
    async def heartbeat(request: Request):
        if not chave_valida(request):
            return JSONResponse({'erro': 'Chave do dispositivo invalida'}, 401)
        corpo = await corpo_json(request)
        if not vinculo_valido(corpo):
            return JSONResponse({'erro': 'Dispositivo/paciente nao autorizado'}, 403)
        with lock:
            dados['contato_em'] = time.monotonic()
            dados['hora_contato'] = datetime.now(timezone.utc).isoformat()
        return {'status': 'ok'}

    @app.post('/api/eventos', tags=['Dispositivo'])
    async def eventos(request: Request):
        if not chave_valida(request):
            return JSONResponse({'erro': 'Chave do dispositivo invalida'}, 401)
        corpo = await corpo_json(request)
        if not isinstance(corpo, dict):
            return JSONResponse({'erro': 'Envie um objeto JSON valido'}, 400)
        if not vinculo_valido(corpo):
            return JSONResponse({'erro': 'Dispositivo/paciente nao autorizado'}, 403)
        faltando = CAMPOS - corpo.keys()
        if faltando:
            return JSONResponse({'erro': 'Campos ausentes', 'campos': sorted(faltando)}, 400)
        if (type(corpo['schemaVersion']) is not int or corpo['schemaVersion'] != 2
                or corpo['eventType'] != 'vitals.state.changed' or corpo['unit'] != 'bpm'
                or type(corpo['state']) is not str or corpo['state'] not in ESTADOS
                or type(corpo['motion']) is not str or corpo['motion'] not in MOVIMENTOS):
            return JSONResponse({'erro': 'Contrato ou campos do evento invalidos'}, 400)
        if (not isinstance(corpo['eventId'], str) or not 1 <= len(corpo['eventId']) <= 100
                or not isinstance(corpo['bootId'], str) or not 1 <= len(corpo['bootId']) <= 24
                or type(corpo['sequence']) is not int or corpo['sequence'] < 1
                or type(corpo['eventTimeMs']) is not int or corpo['eventTimeMs'] < 0
                or not isinstance(corpo['reason'], str) or len(corpo['reason']) > 100):
            return JSONResponse({'erro': 'Identificadores ou sequencia invalidos'}, 400)
        if corpo['eventId'] != f"{device_id}-{corpo['bootId']}-{corpo['sequence']}":
            return JSONResponse({'erro': 'eventId inconsistente'}, 400)
        for nome in ('coverageFc', 'coverageMov'):
            valor = corpo[nome]
            if type(valor) not in (float, int) or not 0 <= valor <= 1:
                return JSONResponse({'erro': f'{nome} invalido'}, 400)
        fc = corpo['value']
        if fc is not None and (type(fc) not in (float, int) or not 0 <= fc <= 250):
            return JSONResponse({'erro': 'value invalido'}, 400)

        with lock:
            if corpo['eventId'] in dados['ids_recentes']:
                dados['duplicados'] += 1
                return JSONResponse({'status': 'duplicado', 'sequence': corpo['sequence']}, 200)
            if corpo['bootId'] != dados['boot_id']:
                if corpo['bootId'] in dados['boots_vistos']:
                    return JSONResponse({'erro': 'Reinicio antigo rejeitado'}, 409)
                dados['boots_vistos'].add(corpo['bootId'])
                dados['boot_id'] = corpo['bootId']
                dados['ultima_seq'] = 0
                dados['ids_recentes'].clear()
            if corpo['sequence'] <= dados['ultima_seq']:
                return JSONResponse({'erro': 'Evento fora de ordem'}, 409)
            if corpo['sequence'] > dados['ultima_seq'] + 1:
                dados['saltos'] += corpo['sequence'] - dados['ultima_seq'] - 1
            dados['ids_recentes'][corpo['eventId']] = True
            if len(dados['ids_recentes']) > 150:
                dados['ids_recentes'].popitem(last=False)
            dados['ultima_seq'] = corpo['sequence']
            dados['evento'] = corpo.copy()
            dados['recebidos'] += 1
            dados['contato_em'] = time.monotonic()
            dados['hora_contato'] = datetime.now(timezone.utc).isoformat()
        return JSONResponse({'status': 'recebido', 'sequence': corpo['sequence']}, 201)

    @app.get('/api/pacientes/{codigo}/estado', tags=['Cuidador'])
    async def estado(request: Request, codigo: str):
        if not autenticado(request):
            return JSONResponse({'erro': 'Faca login'}, 401)
        if request.session.get('paciente') != codigo:
            return JSONResponse({'erro': 'Sem permissao para este paciente'}, 403)
        with lock:
            vivo = dados['contato_em'] is not None and (time.monotonic() - dados['contato_em'] < 120)
            evento = dados['evento']
            expirar_comandos()
            ultimo = next(reversed(dados['comandos'].values()), None)
            return {
                'paciente': codigo,
                'dispositivo': device_id,
                'online': vivo,
                'ultimoContatoUtc': dados['hora_contato'],
                'estado': evento['state'] if evento else 'SEM_EVENTOS',
                'ultimoEvento': evento,
                'eventosRecebidos': dados['recebidos'],
                'eventosDuplicados': dados['duplicados'],
                'saltosDeSequencia': dados['saltos'],
                'ultimoComando': publico(ultimo) if ultimo else None,
            }

    # ------------------------------------------------------------------
    # Ciclo 2: cuidador (produtor) -> API -> ESP32 (consumidor) -> ack (produtor) -> painel
    # ------------------------------------------------------------------
    def csrf_header(request):
        esperado = request.session.get('csrf', '')
        recebido = request.headers.get('X-CSRF-Token', '')
        return bool(esperado and recebido and hmac.compare_digest(esperado, recebido))

    def expirar_comandos():
        agora = time.monotonic()
        for c in dados['comandos'].values():
            if c['status'] in ('PENDENTE', 'ENTREGUE') and agora - c['_criado'] > TTL_COMANDO_S:
                c['status'] = 'EXPIRADO'

    def publico(c):
        return {k: v for k, v in c.items() if not k.startswith('_')}

    @app.post('/api/pacientes/{codigo}/comandos', tags=['Cuidador'])
    async def criar_comando(request: Request, codigo: str):
        if not autenticado(request):
            return JSONResponse({'erro': 'Faca login'}, 401)
        if request.session.get('paciente') != codigo:
            return JSONResponse({'erro': 'Sem permissao para este paciente'}, 403)
        if not csrf_header(request):
            return JSONResponse({'erro': 'Token CSRF ausente ou invalido'}, 403)
        corpo = await corpo_json(request)
        if not isinstance(corpo, dict) or corpo.get('tipo') not in TIPOS_COMANDO:
            return JSONResponse({'erro': 'Tipo de comando invalido',
                                 'permitidos': sorted(TIPOS_COMANDO)}, 400)
        with lock:
            expirar_comandos()
            evento = dados['evento']
            if not evento or evento['state'] != 'ATENCAO':
                return JSONResponse({'erro': 'Nao ha alerta ativo para reconhecer'}, 409)
            # Idempotencia: clique repetido nao cria segundo comando em aberto.
            for c in dados['comandos'].values():
                if c['tipo'] == corpo['tipo'] and c['status'] in ('PENDENTE', 'ENTREGUE'):
                    return JSONResponse(publico(c), 200)
            comando_id = 'cmd-' + secrets.token_hex(6)
            c = {'commandId': comando_id, 'tipo': corpo['tipo'], 'deviceId': device_id,
                 'entityId': patient_id, 'emitidoPor': cuidador, 'status': 'PENDENTE',
                 'criadoEmUtc': datetime.now(timezone.utc).isoformat(),
                 'resultado': None, 'confirmadoEmUtc': None, '_criado': time.monotonic()}
            dados['comandos'][comando_id] = c
            while len(dados['comandos']) > 50:
                dados['comandos'].popitem(last=False)
            return JSONResponse(publico(c), 201)

    @app.get('/api/dispositivo/comandos', tags=['Dispositivo'])
    async def comandos_pendentes(request: Request, deviceId: str = '', entityId: str = ''):
        if not chave_valida(request):
            return JSONResponse({'erro': 'Chave do dispositivo invalida'}, 401)
        if not vinculo_valido({'deviceId': deviceId, 'entityId': entityId}):
            return JSONResponse({'erro': 'Dispositivo/paciente nao autorizado'}, 403)
        with lock:
            expirar_comandos()
            dados['contato_em'] = time.monotonic()
            dados['hora_contato'] = datetime.now(timezone.utc).isoformat()
            pendentes = []
            for c in dados['comandos'].values():
                if c['status'] in ('PENDENTE', 'ENTREGUE'):   # ENTREGUE: reentrega ate o ack
                    c['status'] = 'ENTREGUE'
                    pendentes.append({'commandId': c['commandId'], 'tipo': c['tipo']})
            return {'comandos': pendentes}

    @app.post('/api/comandos/{comando_id}/ack', tags=['Dispositivo'])
    async def ack_comando(request: Request, comando_id: str):
        if not chave_valida(request):
            return JSONResponse({'erro': 'Chave do dispositivo invalida'}, 401)
        corpo = await corpo_json(request)
        if not vinculo_valido(corpo):
            return JSONResponse({'erro': 'Dispositivo/paciente nao autorizado'}, 403)
        if corpo.get('commandId') != comando_id or corpo.get('resultado') not in RESULTADOS_ACK:
            return JSONResponse({'erro': 'Ack invalido'}, 400)
        with lock:
            expirar_comandos()
            c = dados['comandos'].get(comando_id)
            if c is None:
                return JSONResponse({'erro': 'Comando desconhecido'}, 404)
            if c['status'] in ('EXECUTADO', 'IGNORADO'):      # ack repetido: idempotente
                return JSONResponse({'status': c['status']}, 200)
            if c['status'] != 'ENTREGUE':
                return JSONResponse({'erro': 'Comando nao esta aguardando ack',
                                     'status': c['status']}, 409)
            c['status'] = c['resultado'] = corpo['resultado']
            c['confirmadoEmUtc'] = datetime.now(timezone.utc).isoformat()
            return JSONResponse({'status': c['status']}, 201)

    return app


if __name__ == '__main__':
    print('Marco 3: abra http://127.0.0.1:5000/login')
    uvicorn.run(create_app(), host='127.0.0.1', port=5000)
