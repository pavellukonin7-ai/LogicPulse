#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
require_root
load_env
docker compose run --rm --no-deps certbot renew --webroot -w /var/www/certbot --quiet
docker compose exec -T nginx nginx -t
docker compose exec -T nginx nginx -s reload
