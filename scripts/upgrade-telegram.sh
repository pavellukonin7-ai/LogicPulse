#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Запустите на сервере от root.'; exit 1; }
incoming="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target="${1:-/opt/logicpulse}"
[[ "$target" == /opt/logicpulse && "$incoming" != "$target" ]] || { echo 'Распакуйте архив отдельно от /opt/logicpulse.'; exit 1; }
[[ -f "$target/backend/app/main.py" && -f "$target/.env" ]] || { echo 'Нужна существующая установка v1.1.'; exit 1; }
umask 077
cd "$target"
staging="$(mktemp -d /root/logicpulse-telegram-update.XXXXXX)"
trap 'rm -rf "$staging"' EXIT
python3 "$incoming/scripts/patch-telegram-compose.py" docker-compose.yml "$staging/docker-compose.yml"
bash scripts/backup.sh
backup="/root/logicpulse-before-telegram-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar --exclude=node_modules --exclude=__pycache__ --exclude=.pytest_cache -czf "$backup" \
  docker-compose.yml .env backend scripts docs site/privacy.html frontend/public/privacy.html README.md
echo "Резервная копия: $backup"
# Build before changing the live configuration or application files.
docker build -t logicpulse-backend:1.1.2 "$incoming/backend"
cp -a "$incoming/backend/." "$target/backend/"
cp -a "$incoming/scripts/." "$target/scripts/"
cp -a "$incoming/docs/." "$target/docs/"
cp "$incoming/README.md" "$target/README.md"
cp "$staging/docker-compose.yml" docker-compose.yml
# Install the updated data-use notice before enabling Telegram.
install -m 644 "$incoming/site/privacy.html" site/privacy.html
install -m 644 "$incoming/frontend/public/privacy.html" frontend/public/privacy.html
install -d -m 755 /run/logicpulse-telegram
docker compose config --quiet
docker compose up -d --no-deps --wait --wait-timeout 150 backend telegram-worker
bash scripts/check.sh
echo 'Обновление установлено. Подключение бота: python3 /opt/logicpulse/scripts/setup-telegram.py'
echo "Копия для восстановления: $backup"
