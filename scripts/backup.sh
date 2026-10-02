#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
require_root
load_env
umask 077
mkdir -p backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="backups/postgres-$stamp.dump"
trap 'rm -f "${target}.tmp"' EXIT
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "${target}.tmp"
[[ -s "${target}.tmp" ]]
mv "${target}.tmp" "$target"
echo "Создан $target. Скопируйте его за пределы сервера."
