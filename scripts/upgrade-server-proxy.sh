#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
src="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target=/opt/logicpulse
config="${1:-/root/logicpulse-happ.json}"
[[ $EUID -eq 0 && -f "$target/.env" && -f "$config" ]] || {
  echo 'Нужен root, /opt/logicpulse/.env и /root/logicpulse-happ.json.' >&2
  exit 1
}
[[ "$src" != "$target" ]] || { echo 'Запустите обновление из распакованного архива в /root.' >&2; exit 1; }
backup="$(mktemp -d /root/logicpulse-proxy-tools-before-XXXXXXXX)"
for item in scripts/install-server-proxy.py docs/SERVER_PROXY.md docs/SERVER_PROXY_VALIDATION.md; do
  if [[ -f "$target/$item" ]]; then
    mkdir -p "$backup/$(dirname "$item")"
    cp -p -- "$target/$item" "$backup/$item"
  fi
  install -D -m 644 -- "$src/$item" "$target/$item"
done
echo "Копия прежних инструкций и установщика: $backup"
python3 "$target/scripts/install-server-proxy.py" --config "$config"
