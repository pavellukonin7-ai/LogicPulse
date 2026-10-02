#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите от root на VPS.'; exit 1; }
incoming="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target=/opt/logicpulse
[[ "$incoming" != "$target" && -f "$target/.env" ]] || { echo 'Распакуйте обновление отдельно в /root.'; exit 1; }
cd "$target"
stage="$(mktemp -d /root/logicpulse-v12-stage-XXXXXXXX)"
trap 'rm -rf -- "$stage"' EXIT
cp docker-compose.yml "$stage/docker-compose.yml"
python3 "$incoming/scripts/patch-v12-compose.py" "$stage/docker-compose.yml"
docker compose --env-file "$target/.env" -f "$stage/docker-compose.yml" config --quiet
bash scripts/backup.sh
backup="/root/logicpulse-before-v1.2-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar --exclude='*/node_modules' --exclude='*/__pycache__' --exclude='*/.pytest_cache' -czf "$backup" \
  docker-compose.yml .env backend frontend site nginx scripts docs README.md
echo "Резервная копия: $backup"
echo 'Сборка frontend перед заменой работающего сайта…'
docker run --rm -v "$incoming/frontend:/work" -w /work node:24-alpine \
  sh -c 'npm ci --no-audit --no-fund && npm run build'
docker build -t logicpulse-backend:1.2.0 "$incoming/backend"
# Validate the new Nginx config against the existing certificate before replacing it.
mkdir -p "$stage/nginx"
python3 - "$target/.env" "$incoming/nginx/templates/production.conf" "$stage/nginx/logicpulse.conf" <<'PY'
from pathlib import Path
import re,sys
values=dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines() if line and not line.startswith('#') and '=' in line)
domain=values['DOMAIN']
if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',domain):raise SystemExit('Invalid domain')
Path(sys.argv[3]).write_text(Path(sys.argv[2]).read_text().replace('__DOMAIN__',domain))
PY
docker run --rm -v "$stage/nginx:/etc/nginx/conf.d:ro" -v "$target/certbot/conf:/etc/letsencrypt:ro" nginx:stable-alpine nginx -t
changed=0
rollback() {
  code=$?
  trap - ERR
  if [[ $changed == 1 ]]; then
    echo 'Обновление остановлено. Восстанавливаю предыдущие файлы и контейнеры…'
    tar -xzf "$backup" -C "$target"
    if ! docker compose up -d --wait --wait-timeout 180; then
      echo "Автоматическое восстановление не завершено. Сохранена копия: $backup"
    fi
  fi
  exit "$code"
}
trap rollback ERR
changed=1
docker compose stop pgadmin registry
for item in backend scripts docs; do cp -a "$incoming/$item/." "$target/$item/"; done
tar -C "$incoming/frontend" --exclude=node_modules --exclude=dist -cf - . | tar -C "$target/frontend" -xf -
cp "$stage/docker-compose.yml" "$target/docker-compose.yml"
cp "$incoming/README.md" "$target/README.md"
cp -a "$incoming/nginx/templates/." "$target/nginx/templates/"
# Preserve the bind-mounted directory inode and prior hashed assets for open tabs.
cp -a "$incoming/frontend/dist/." "$target/site/"
bash scripts/prepare-app.sh
python3 scripts/render-config.py production
docker compose up --build -d --wait --wait-timeout 180
bash scripts/check.sh
trap - ERR
cat > /etc/systemd/system/logicpulse-housekeeping.service <<'UNIT'
[Unit]
Description=LogicPulse expired sessions and analytics retention
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
WorkingDirectory=/opt/logicpulse
ExecStart=/usr/bin/docker compose exec -T backend python -m app.manage housekeeping
UNIT
cat > /etc/systemd/system/logicpulse-housekeeping.timer <<'UNIT'
[Unit]
Description=LogicPulse daily retention cleanup
[Timer]
OnCalendar=*-*-* 04:15:00 UTC
RandomizedDelaySec=600
Persistent=true
[Install]
WantedBy=timers.target
UNIT
chmod 644 /etc/systemd/system/logicpulse-housekeeping.{service,timer}
systemctl daemon-reload
systemctl enable --now logicpulse-housekeeping.timer
echo 'Обновление 1.2 установлено. Создайте администратора:'
echo 'cd /opt/logicpulse && docker compose exec backend python -m app.manage admin'
echo 'Инструкция и проверка задания: docs/ADMIN_V1.2.md'
echo "Копия для отката: $backup"
