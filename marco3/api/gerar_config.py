"""Prepara credenciais locais de DEMONSTRACAO, sem dependencia de Neon."""

import secrets
from pathlib import Path
import hashlib

BASE = Path(__file__).resolve().parent
ENV = BASE / '.env'
CONFIG_ESP32 = BASE.parent / 'produtor' / 'config.h'


def main():
    if ENV.exists() or CONFIG_ESP32.exists():
        print('Configuracao ja existe. Para preservar credenciais, nada foi alterado.')
        print('Se precisar recriar, exclua manualmente api/.env e produtor/config.h.')
        return

    device_key = secrets.token_urlsafe(32)
    app_secret = secrets.token_urlsafe(40)
    senha = secrets.token_urlsafe(10)
    salt = secrets.token_bytes(16)
    resultado = hashlib.scrypt(senha.encode(), salt=salt, n=2**14, r=8, p=1)
    hash_senha = f'scrypt${salt.hex()}${resultado.hex()}'
    ENV.write_text(
        f'APP_SECRET_KEY={app_secret}\n'
        f'DEVICE_API_KEY={device_key}\n'
        f'CUIDADOR_USUARIO=cuidador01\n'
        f'CUIDADOR_SENHA_HASH={hash_senha}\n'
        f'DEVICE_ID=esp32-borda-01\n'
        f'PATIENT_ID=patient-0042\n'
        f'COOKIE_SECURE=0\n',
        encoding='utf-8',
    )
    CONFIG_ESP32.write_text(
        '#pragma once\n'
        '// NAO publique este arquivo (GitHub ou Wokwi publico): contem a chave do ESP32.\n'
        '// Troque a URL abaixo pela que o comando "cloudflared tunnel --url http://127.0.0.1:5000"\n'
        '// mostrar, usando http:// (o Wokwi nao completa HTTPS; as mensagens vao assinadas).\n'
        'const char* API_BASE_URL = "http://COLE-AQUI-A-URL-DO-TUNEL.trycloudflare.com";\n'
        f'const char* DEVICE_API_KEY = "{device_key}";\n',
        encoding='utf-8',
    )
    try:
        ENV.chmod(0o600)
        CONFIG_ESP32.chmod(0o600)
    except OSError:
        pass
    print('Arquivos criados: api/.env e produtor/config.h')
    print('Guarde esta senha: ela so sera exibida agora.')
    print('Usuario: cuidador01')
    print(f'Senha: {senha}')
    print('Nao publique .env nem config.h no GitHub.')
    print('Proximo passo: inicie a API e o tunel e cole a URL em produtor/config.h (com http://)')


if __name__ == '__main__':
    main()
