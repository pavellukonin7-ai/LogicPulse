#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Запустите на VPS от root.'; exit 1; }
incoming="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target="${1:-/opt/logicpulse}"
[[ "$target" == /opt/logicpulse && "$incoming" != "$target" ]] || {
  echo 'Распакуйте обновление отдельно (например, /root/LogicPulse_Server_v1.1.0).'; exit 1;
}
[[ -f "$target/.env" && -f "$target/docker-compose.yml" && -s "$incoming/site/index.html" ]] || {
  echo 'Не найдена существующая установка или сборка обновления.'; exit 1;
}
cd "$target"
docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
bash scripts/backup.sh
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="/root/logicpulse-before-v1.1-$stamp.tar.gz"
items=(docker-compose.yml .env site nginx scripts docs create-user.sh README.md)
for item in backend frontend; do [[ ! -e "$item" ]] || items+=("$item"); done
umask 077
tar -czf "$backup" "${items[@]}"
echo "Копия конфигурации и сайта: $backup"
# Build before replacing any live application files; the compiled site is also
# supplied in the archive for inspection. Runtime secrets never enter this build.
docker run --rm -v "$incoming/frontend:/work" -w /work node:24-alpine \
  sh -c 'npm ci --no-audit --no-fund && npm run build'
for item in backend frontend scripts docs; do
  mkdir -p "$target/$item"
done
cp -a "$incoming/backend/." "$target/backend/"
# Do not copy node_modules or any private deployment files.
tar -C "$incoming/frontend" --exclude=node_modules --exclude=dist -cf - . | tar -C "$target/frontend" -xf -
cp -a "$incoming/scripts/." "$target/scripts/"
cp -a "$incoming/docs/." "$target/docs/"
cp "$incoming/docker-compose.yml" "$incoming/create-user.sh" "$incoming/README.md" "$target/"
cp -a "$incoming/nginx/templates/." "$target/nginx/templates/"
bash scripts/prepare-app.sh
docker compose config --quiet
docker compose build backend
docker compose up -d --wait --wait-timeout 150 postgres backend
# Keep the bind-mounted directory inode and old hashed assets for open browser tabs.
# The new index is installed last.
for item in "$incoming/frontend/dist/"*; do
  [[ "$(basename "$item")" == index.html ]] || cp -a "$item" "$target/site/"
done
cp "$incoming/frontend/dist/index.html" "$target/site/index.html.new"
chmod 644 "$target/site/index.html.new"
mv "$target/site/index.html.new" "$target/site/index.html"
bash scripts/prepare-app.sh
python3 scripts/render-config.py production
if ! docker compose exec -T nginx nginx -t; then
  tar -xzf "$backup" -C "$target" nginx site
  echo "Nginx не изменён: восстановлена конфигурация. Копия: $backup"
  exit 1
fi
docker compose exec -T nginx nginx -s reload
bash scripts/check.sh
echo 'Обновление выполнено. Следующий шаг: docs/START_HERE.md — создание пяти услуг через /docs.'
