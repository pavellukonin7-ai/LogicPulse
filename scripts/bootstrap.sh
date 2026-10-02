#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
require_root
bash scripts/prepare-app.sh
load_env
[[ -s auth/htpasswd ]] || { echo 'Сначала bash create-user.sh pavel'; exit 1; }
command -v docker >/dev/null
# Check DNS without changing it. Port 80 must be reachable publicly for ACME.
if ! getent ahostsv4 "$DOMAIN" | awk '{print $1}' | grep -Fxq "$SERVER_IP"; then
  echo "DNS $DOMAIN не указывает на $SERVER_IP. Исправьте A-запись перед запуском."; exit 1
fi
# Do not replace an already-running deployment or take ports from another stack.
if [[ ! -s "certbot/conf/live/$DOMAIN/fullchain.pem" ]]; then
  for port in 80 443 5000 5050; do
    if ss -H -ltn "sport = :$port" | grep -q .; then
      if ! docker compose ps --status running --services | grep -qx nginx; then
        echo "Порт $port занят. Проверьте ss -lntp; существующие сервисы не остановлены."; exit 1
      fi
    fi
  done
  echo 'Сертификат будет выпущен Let’s Encrypt: https://letsencrypt.org/repository/'
  read -r -p 'Принимаете условия Let’s Encrypt для выпуска сертификата? [yes/NO]: ' accepted
  [[ "$accepted" == yes ]] || { echo 'Выпуск сертификата отменён.'; exit 1; }
  python3 scripts/render-config.py bootstrap
  docker compose config --quiet
  docker compose pull nginx postgres pgadmin registry watchtower
  docker compose up -d nginx
  docker compose run --rm --no-deps certbot certonly --webroot -w /var/www/certbot \
    --cert-name "$DOMAIN" -d "$DOMAIN" --email "$LETSENCRYPT_EMAIL" \
    --agree-tos --non-interactive --keep-until-expiring
fi
python3 scripts/render-config.py production
docker compose config --quiet
# Validate before reloading the running web server.
docker compose run --rm --no-deps nginx nginx -t
docker compose up -d --build
docker compose exec -T nginx nginx -s reload
echo 'Запуск выполнен. Проверка: bash scripts/check.sh'
