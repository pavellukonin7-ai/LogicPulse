#!/usr/bin/env bash
set -Eeuo pipefail
incoming="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target="${1:-/opt/logicpulse}"
bash "$incoming/scripts/upgrade-telegram.sh" "$target"
cd "$target"
python3 scripts/enable-windows-proxy.py
python3 scripts/setup-telegram.py
