#!/usr/bin/env bash
set -Eeuo pipefail
cd /opt/logicpulse
docker compose exec -T backend python -m app.manage seed-tests
