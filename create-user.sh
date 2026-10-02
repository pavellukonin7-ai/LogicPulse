#!/usr/bin/env bash
source "$(dirname "$0")/scripts/common.sh"
require_root
command -v htpasswd >/dev/null || { echo 'Сначала установите окружение: bash scripts/install-docker.sh'; exit 1; }
username="${1:-}"
[[ -n "$username" ]] || read -r -p 'Имя пользователя Registry: ' username
[[ "$username" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$ ]] || { echo 'Допустимы буквы, цифры, _, . и -'; exit 1; }
mkdir -p auth
chmod 755 auth
# No -c: preserve existing users. bcrypt is mandatory for Distribution Registry.
touch auth/htpasswd
htpasswd -B -C 12 auth/htpasswd "$username"
chmod 644 auth/htpasswd
# Hashes only; passwords are never passed as command arguments or written in plaintext.
if [[ -f .env ]] && docker compose ps --status running --services 2>/dev/null | grep -qx registry; then
  docker compose restart registry
fi
echo "Пользователь $username готов. При перезапуске Registry активные загрузки прерываются."
