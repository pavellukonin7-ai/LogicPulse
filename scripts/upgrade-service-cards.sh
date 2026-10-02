#!/usr/bin/env bash
set -Eeuo pipefail
incoming="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
echo 'Текущий пакет объединяет обновление карточек и оформление Living Pulse.'
exec bash "$incoming/scripts/upgrade-living-pulse.sh" "${1:-/opt/logicpulse}"
