"""Cria credenciais privadas e sincroniza a chave entre API e Wokwi.

Usa o desenho da branch marco3-enxuto: config.h e .env NAO vao ao GitHub.
Rodar novamente preserva as credenciais existentes (inclusive DATABASE_URL).
"""

import hashlib
import re
import secrets
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV = BASE / '.env'
CONFIG_ESP32 = BASE.parent / 'produtor' / 'config.h'


def _ler_chave_env():
    if not ENV.exists():
        return None
    for linha in ENV.read_text(encoding='utf-8').splitlines():
        if linha.startswith('DEVICE_API_KEY='):
            return linha.split('=', 1)[1].strip()
    return None


def _ler_chave_esp32():
    if not CONFIG_ESP32.exists():
        return None
    match = re.search(r'DEVICE_API_KEY\s*=\s*"([^"]+)"',
                      CONFIG_ESP32.read_text(encoding='utf-8'))
    return match.group(1) if match else None


def main():
    chave_api = _ler_chave_env()
    chave_esp32 = _ler_chave_esp32()
    if chave_api and chave_esp32 and chave_api != chave_esp32:
        raise SystemExit('ERRO: as chaves de api/.env e produtor/config.h sao diferentes. '
                         'Conserte manualmente para usar a MESMA chave; nada foi sobrescrito.')
    chave = chave_api or chave_esp32 or secrets.token_urlsafe(32)

    if not ENV.exists():
        senha = secrets.token_urlsafe(10)
        sal = secrets.token_bytes(16)
        derivada = hashlib.scrypt(senha.encode(), salt=sal, n=2**14, r=8, p=1)
        hash_senha = f'scrypt${sal.hex()}${derivada.hex()}'
        ENV.write_text(
            f'APP_SECRET_KEY={secrets.token_urlsafe(40)}\n'
            f'DEVICE_API_KEY={chave}\n'
            f'CUIDADOR_USUARIO=cuidador01\n'
            f'CUIDADOR_SENHA_HASH={hash_senha}\n'
            f'DEVICE_ID=esp32-borda-01\n'
            f'PATIENT_ID=patient-0042\n'
            f'COOKIE_SECURE=0\n', encoding='utf-8')
        print('[OK] api/.env criado. Copie a senha agora e guarde-a em local privado.')
        print('Usuario: cuidador01')
        print(f'Senha: {senha}')
    else:
        print('[OK] api/.env existente preservado (incluindo DATABASE_URL).')
        if not chave_api:
            raise SystemExit('ERRO: api/.env existe sem DEVICE_API_KEY; corrija antes de continuar.')

    if not CONFIG_ESP32.exists():
        CONFIG_ESP32.write_text(
            '#pragma once\n'
            '// Arquivo privado: NAO publicar no GitHub nem em Wokwi publico.\n'
            '// Troque a URL pela URL atual do tunel com http://.\n'
            'const char* API_BASE_URL = "http://COLE-AQUI-A-URL-DO-TUNEL.trycloudflare.com";\n'
            f'const char* DEVICE_API_KEY = "{chave}";\n', encoding='utf-8')
        print('[OK] produtor/config.h criado com a chave compartilhada com a API.')
    else:
        print('[OK] produtor/config.h existente preservado.')
    for path in [ENV, CONFIG_ESP32]:
        try:
            path.chmod(0o600)
        except OSError:
            pass
    print('Nao publique .env, config.h nem a URL DATABASE_URL no GitHub.')


if __name__ == '__main__':
    main()
