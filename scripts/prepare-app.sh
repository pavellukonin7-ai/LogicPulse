#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
require_root
[[ -f .env ]] || { echo 'Сначала настройте .env'; exit 1; }
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.env')
lines = p.read_text().splitlines()
matches = [i for i, line in enumerate(lines) if line.startswith('ADMIN_API_KEY=')]
if len(matches) > 1:
    raise SystemExit('В .env несколько ADMIN_API_KEY: исправьте дубликат.')
if not matches or not lines[matches[0]].split('=', 1)[1].strip():
    value = 'ADMIN_API_KEY=' + secrets.token_hex(32)
    if matches:
        lines[matches[0]] = value
    else:
        lines.append(value)
    p.write_text('\n'.join(lines) + '\n')
p.chmod(0o600)
print('Ключ администратора подготовлен в .env (значение не выводится).')
PY
# Limit permission changes to public assets and the directory Nginx must traverse.
for dir in site registry-ui nginx/conf.d auth; do
  [[ ! -d "$dir" ]] || chmod 755 "$dir"
done
for dir in site registry-ui; do
  [[ ! -d "$dir" ]] || find "$dir" -type d -exec chmod 755 {} +
  [[ ! -d "$dir" ]] || find "$dir" -type f -exec chmod 644 {} +
done
[[ ! -f auth/htpasswd ]] || chmod 644 auth/htpasswd
