#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
require_root
if [[ -e .env ]]; then echo '.env уже существует; доступы не изменены.'; exit 0; fi
umask 077
read -r -p 'Email для сертификата Let’s Encrypt: ' ssl_email
read -r -p 'Email для входа в pgAdmin (Enter = тот же): ' admin_email
admin_email="${admin_email:-$ssl_email}"
python3 - "$ssl_email" "$admin_email" <<'PYTHON'
import json, os, re, secrets, sys
from pathlib import Path
ssl, admin = sys.argv[1:]
for email in (ssl, admin):
    if not re.fullmatch(r'[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', email):
        raise SystemExit('Введите корректный email без пробелов.')
values = dict(DOMAIN='logicpulse.ru', SERVER_IP='185.125.218.116', LETSENCRYPT_EMAIL=ssl,
              POSTGRES_DB='logicpulse', POSTGRES_USER='logicpulse_admin',
              POSTGRES_PASSWORD=secrets.token_hex(32), PGADMIN_DEFAULT_EMAIL=admin,
              PGADMIN_DEFAULT_PASSWORD=secrets.token_hex(32), REGISTRY_HTTP_SECRET=secrets.token_hex(32), ADMIN_API_KEY=secrets.token_hex(32))
with open('.env', 'x') as f:
    f.write('# Secrets: generated on the server. Do not share or commit.\n')
    f.writelines(f'{k}={v}\n' for k,v in values.items())
os.chmod('.env', 0o600)
PYTHON
echo '.env создан с уникальными паролями и правами 600. Просмотр на сервере: nano .env'
