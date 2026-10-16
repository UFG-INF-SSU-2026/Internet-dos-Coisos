"""Prepara o api/.env de DEMONSTRACAO.

A chave do dispositivo e fixa e versionada em produtor/config.h (decisao D11):
este script so a copia para o .env, para API e ESP32 usarem a mesma.
"""

import re
import secrets
from pathlib import Path
import hashlib

BASE = Path(__file__).resolve().parent
ENV = BASE / '.env'
CONFIG_ESP32 = BASE.parent / 'produtor' / 'config.h'


def main():
    if ENV.exists():
        print('api/.env ja existe. Para preservar a senha, nada foi alterado.')
        print('Se precisar recriar, exclua manualmente api/.env.')
        return

    achou = re.search(r'DEVICE_API_KEY = "([^"]+)"', CONFIG_ESP32.read_text(encoding='utf-8'))
    if not achou:
        raise SystemExit('Nao encontrei DEVICE_API_KEY em produtor/config.h')
    device_key = achou.group(1)
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
    try:
        ENV.chmod(0o600)
    except OSError:
        pass
    print('Arquivo criado: api/.env (chave do dispositivo copiada de produtor/config.h)')
    print('Guarde esta senha: ela so sera exibida agora.')
    print('Usuario: cuidador01')
    print(f'Senha: {senha}')
    print('Nao publique o .env no GitHub (senha e segredo da sessao).')
    print('Proximo passo: inicie a API e o tunel e troque a URL em config.h no Wokwi (com http://)')


if __name__ == '__main__':
    main()
