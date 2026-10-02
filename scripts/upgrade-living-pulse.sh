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
# Refuse unknown local edits before touching the running installation.
python3 - "$incoming" "$target" <<'PY'
import hashlib, json, sys
from pathlib import Path
incoming, target = map(Path, sys.argv[1:])
manifest = json.loads((incoming/'scripts/living-pulse-manifest.json').read_text())
for relative, hashes in manifest.items():
    source, existing = incoming/relative, target/relative
    if hashlib.sha256(source.read_bytes()).hexdigest() != hashes['after']:
        raise SystemExit('Повреждён файл обновления: ' + relative)
    actual = hashlib.sha256(existing.read_bytes()).hexdigest() if existing.exists() else None
    if actual not in (*hashes['accepted'], hashes['after']):
        raise SystemExit('Есть локальные изменения в ' + relative + '. Обновление остановлено до замены файлов. Пришлите только это сообщение.')
print('Совместимость файлов подтверждена.')
PY
container_id="$(docker compose ps -q backend)"
[[ -n "$container_id" ]] || { echo 'Сначала запустите текущий backend.'; exit 1; }
old_image="$(docker inspect --format '{{.Image}}' "$container_id")"
backend_changed=0
for name in models.py schemas.py main.py; do
  cmp -s "$incoming/backend/app/$name" "backend/app/$name" || backend_changed=1
done
image_tag="$(docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["backend"]["image"])')"
stage="$(mktemp -d /root/logicpulse-living-stage-XXXXXXXX)"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
new_image="logicpulse-backend:living-$(date -u +%s)-$$"
trap 'rm -rf -- "$stage"' EXIT
bash scripts/backup.sh
backup="/root/logicpulse-before-living-pulse-${stamp}.tar.gz"
tar --exclude='*/node_modules' --exclude='*/dist' --exclude='*/__pycache__' --exclude='*/.pytest_cache' \
  -czf "$backup" docker-compose.yml .env backend frontend site
echo "Резервная копия: $backup"
printf '%s\n' "$old_image" > "$backup.image-id"
mkdir -p "$stage/backend" "$stage/frontend"
tar -C backend --exclude=__pycache__ --exclude=.pytest_cache -cf - . | tar -C "$stage/backend" -xf -
tar -C frontend --exclude=node_modules --exclude=dist -cf - . | tar -C "$stage/frontend" -xf -
for name in models.py schemas.py main.py; do
  cp "$incoming/backend/app/$name" "$stage/backend/app/$name"
done
for name in account.html account.js app.js admin.js admin.html index.html i18n.js i18n-strings.js language.css privacy.html privacy.js service-card.js service-cards.css service-locales.js service-templates.js service-translations.js living-services.js living-pulse.css living-motion.js vite.config.js; do
  cp "$incoming/frontend/$name" "$stage/frontend/$name"
done
mkdir -p "$stage/frontend/public/art" "$stage/frontend/public/fonts"
cp "$incoming/frontend/public/art/living-pulse-"*.svg "$stage/frontend/public/art/"
cp "$incoming/frontend/public/fonts/onest-"*.woff "$incoming/frontend/public/fonts/OFL.txt" "$stage/frontend/public/fonts/"
cp "$incoming/frontend/public/fonts/noto-sans-sc.woff" "$incoming/frontend/public/fonts/NotoSansSC-OFL.txt" "$stage/frontend/public/fonts/"
echo 'Сборка Living Pulse перед заменой работающего приложения…' 
docker run --rm -v "$stage/frontend:/work" -w /work node:24-alpine \
  sh -c 'npm ci --no-audit --no-fund && npm run build'
python3 - "$stage/frontend/dist" <<'PY_CHECK'
from pathlib import Path
import re,sys
root=Path(sys.argv[1]); html=(root/'index.html').read_text()
assert 'data-design="living-pulse-static"' in html
assert 'data-motion-version="1"' in html
assert 'data-languages="ru,en,zh"' in html
for name in ('account.html','privacy.html'):
    assert (root/name).is_file(), 'Missing page: '+name
for url in re.findall(r'(?:src|href)="(/(?:assets|art|fonts)/[^"?#]+)',html):
    assert (root/url.lstrip('/')).is_file(), 'Missing asset: '+url
assert (root/'fonts/onest-300.woff').stat().st_size > 10000
assert (root/'fonts/noto-sans-sc.woff').stat().st_size > 50000
print('OK: три языка, HTML, стили, скрипты, шрифты и графика собраны.')
PY_CHECK
if [[ $backend_changed == 1 ]]; then
  docker build -t "$new_image" "$stage/backend"
fi
changed=0
restore_backend() {
  if [[ $backend_changed == 1 ]]; then
    docker tag "$old_image" "$image_tag" && \
      docker compose up -d --no-deps --force-recreate --wait --wait-timeout 180 backend
  fi
}
rollback() {
  code=$?
  trap - ERR
  if [[ $changed == 1 ]]; then
    echo 'Проверка не прошла. Восстанавливаю прежние файлы и образ backend…'
    if tar -xzf "$backup" -C "$target" && restore_backend; then
      echo 'Прежняя версия восстановлена.'
    else
      echo "Автоматический откат не завершён. Сохранена копия: $backup"
    fi
  fi
  exit "$code"
}
trap rollback ERR
changed=1
for name in models.py schemas.py main.py; do
  cp "$stage/backend/app/$name" "backend/app/$name"
done
for name in account.html account.js app.js admin.js admin.html index.html i18n.js i18n-strings.js language.css privacy.html privacy.js service-card.js service-cards.css service-locales.js service-templates.js service-translations.js living-services.js living-pulse.css living-motion.js vite.config.js; do
  cp "$stage/frontend/$name" "frontend/$name"
done
mkdir -p frontend/public/art frontend/public/fonts
cp "$stage/frontend/public/art/living-pulse-"*.svg frontend/public/art/
cp "$stage/frontend/public/fonts/onest-"*.woff "$stage/frontend/public/fonts/OFL.txt" frontend/public/fonts/
cp "$stage/frontend/public/fonts/noto-sans-sc.woff" "$stage/frontend/public/fonts/NotoSansSC-OFL.txt" frontend/public/fonts/
if [[ $backend_changed == 1 ]]; then
  docker tag "$new_image" "$image_tag"
  docker compose up -d --no-deps --force-recreate --wait --wait-timeout 180 backend
else
  echo 'Backend уже совместим. Обновляется только оформление сайта.'
fi
# Publish only after the backend accepts the new service fields. Keep old hashed assets
# and the bind-mounted directory inode for currently open browser tabs.
cp -a "$stage/frontend/dist/." site/
find site -type d -exec chmod 755 {} +
find site -type f -exec chmod 644 {} +
docker compose exec -T backend python - <<'PY'
import json, urllib.request
from app.database import SessionLocal
from sqlalchemy import text
with SessionLocal() as db:
    db.execute(text('SELECT count(*) FROM lp_service_details'))
schema = json.load(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=10))
assert 'delivery_time' in schema['components']['schemas']['ServicePublic']['properties']
print('OK: API и таблица дополнительных полей услуг готовы.')
PY
docker compose exec -T nginx nginx -t
bash scripts/check.sh
domain="$(python3 - <<'PY_DOMAIN'
from pathlib import Path
for line in Path('.env').read_text().splitlines():
    if line.startswith('DOMAIN='):
        print(line.split('=',1)[1].strip().strip('"').strip("'")); break
PY_DOMAIN
)"
[[ "$domain" =~ ^[a-zA-Z0-9.-]+$ ]]
curl --fail --silent --show-error --max-time 20 "https://$domain/" | \
  python3 -c 'import sys; html=sys.stdin.read(); assert "data-motion-version=\"1\"" in html and "data-languages=\"ru,en,zh\"" in html, "Сайт пока отдаёт прежний HTML"'
trap - ERR
mkdir -p docs
cp "$incoming/docs/LIVING_PULSE.md" docs/LIVING_PULSE.md
cp "$incoming/docs/SERVICE_CARDS.md" docs/SERVICE_CARDS.md
cp "$incoming/docs/LANGUAGES.md" docs/LANGUAGES.md
echo 'Готово: RU / EN / 中文 установлены. Откройте https://logicpulse.ru/ и обновите страницу Ctrl+F5.'
echo 'Движение при прокрутке включено. Услуги и цены читаются из вашей базы.'
echo 'Если цены или сроки ещё не заполнены: Управление → Услуги → Изменить → проверьте поля и сохраните.'
echo "Резервная копия: $backup"
