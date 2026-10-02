#!/usr/bin/env bash
# Incremental patch for the existing LogicPulse 1.2 installation.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите от root на VPS.'; exit 1; }
incoming="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target="$(realpath "${1:-/opt/logicpulse}")"
[[ "$incoming" != "$target" && -f "$target/.env" ]] || { echo 'Распакуйте обновление отдельно от /opt/logicpulse.'; exit 1; }
cd "$target"
docker compose config --quiet
# Never silently replace a locally customized account or auth implementation.
python3 - "$incoming" "$target" <<'PY'
import hashlib, json, sys
from pathlib import Path
incoming, target = map(Path, sys.argv[1:])
manifest = json.loads((incoming/'scripts/remember-me-manifest.json').read_text())
for relative, hashes in manifest.items():
    source, existing = incoming/relative, target/relative
    if hashlib.sha256(source.read_bytes()).hexdigest() != hashes['after']:
        raise SystemExit('Повреждён файл обновления: ' + relative)
    actual = hashlib.sha256(existing.read_bytes()).hexdigest() if existing.exists() else None
    if actual not in (hashes['before'], hashes['after']):
        raise SystemExit('Есть локальные изменения в ' + relative + '. Обновление остановлено до замены файлов. Пришлите только это сообщение.')
print('Совместимость файлов подтверждена.')
PY
container_id="$(docker compose ps -q backend)"
[[ -n "$container_id" ]] || { echo 'Сначала запустите текущий backend.'; exit 1; }
old_image="$(docker inspect --format '{{.Image}}' "$container_id")"
image_tag="$(docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["backend"]["image"])')"
stage="$(mktemp -d /root/logicpulse-remember-stage-XXXXXXXX)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
new_image="logicpulse-backend:remember-$(date -u +%s)-$$"
trap 'rm -rf -- "$stage"' EXIT
bash scripts/backup.sh
backup="/root/logicpulse-before-remember-${stamp}.tar.gz"
tar --exclude='*/node_modules' --exclude='*/dist' --exclude='*/__pycache__' --exclude='*/.pytest_cache' \
  -czf "$backup" docker-compose.yml .env backend frontend site
echo "Резервная копия: $backup"
printf '%s\n' "$old_image" > "$backup.image-id"
mkdir -p "$stage/backend" "$stage/frontend"
tar -C backend --exclude=__pycache__ --exclude=.pytest_cache -cf - . | tar -C "$stage/backend" -xf -
tar -C frontend --exclude=node_modules --exclude=dist -cf - . | tar -C "$stage/frontend" -xf -
cp "$incoming/backend/app/auth.py" "$stage/backend/app/auth.py"
for name in account.html account.js remember-me.css public/privacy.html; do
  cp "$incoming/frontend/$name" "$stage/frontend/$name"
done
echo 'Сборка обновления перед заменой работающего приложения…'
docker run --rm -v "$stage/frontend:/work" -w /work node:24-alpine \
  sh -c 'npm ci --no-audit --no-fund && npm run build'
docker build -t "$new_image" "$stage/backend"
changed=0
rollback() {
  code=$?
  trap - ERR
  if [[ $changed == 1 ]]; then
    echo 'Проверка не прошла. Восстанавливаю прежние файлы и образ backend…'
    if tar -xzf "$backup" -C "$target" && docker tag "$old_image" "$image_tag" && \
      docker compose up -d --no-deps --force-recreate --wait --wait-timeout 180 backend; then
      echo 'Прежняя версия восстановлена.'
    else
      echo "Автоматический откат не завершён. Сохранена копия: $backup"
    fi
  fi
  exit "$code"
}
trap rollback ERR
changed=1
cp "$stage/backend/app/auth.py" backend/app/auth.py
for name in account.html account.js remember-me.css public/privacy.html; do
  cp "$stage/frontend/$name" "frontend/$name"
done
docker tag "$new_image" "$image_tag"
docker compose up -d --no-deps --force-recreate --wait --wait-timeout 180 backend
# Publish only after the backend accepts remember_me. Keep old hashed assets
# and the bind-mounted directory inode for currently open browser tabs.
cp -a "$stage/frontend/dist/." site/
find site -type d -exec chmod 755 {} +
find site -type f -exec chmod 644 {} +
docker compose exec -T backend python - <<'PY'
import json, urllib.request
from app.auth import TTL, REMEMBER_TTL
assert TTL == 43200 and REMEMBER_TTL == 2592000
schema = json.load(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=10))
assert schema['components']['schemas']['BrowserCredentials']['properties']['remember_me']['default'] is False
print('OK: backend поддерживает вход на 12 часов и 30 дней.')
PY
docker compose exec -T nginx nginx -t
bash scripts/check.sh
trap - ERR
mkdir -p docs
cp "$incoming/docs/REMEMBER_ME.md" docs/REMEMBER_ME.md
echo 'Готово: «Запомнить меня на 30 дней» добавлено во вход и регистрацию.'
echo 'В браузере обновите страницу аккаунта Ctrl+F5, выйдите и войдите с галочкой.'
echo 'У существующих сеансов срок не изменяется. Пароли и данные аккаунтов сохранены.'
echo "Резервная копия: $backup"
