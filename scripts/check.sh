#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
load_env
docker compose ps
fail=0
running="$(docker compose ps --status running --services)"
for service in nginx postgres watchtower backend; do
  if grep -Fxq "$service" <<< "$running"; then echo "RUNNING $service"; else echo "NOT RUNNING $service"; fail=1; fi
done
if [[ "${TELEGRAM_ENABLED:-false}" == true ]]; then
  if grep -Fxq telegram-worker <<< "$running"; then echo 'RUNNING telegram-worker'; else echo 'NOT RUNNING telegram-worker'; fail=1; fi
fi
check() {
  local url="$1" expected="$2" code
  code=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --retry 4 --retry-delay 2 --retry-connrefused --connect-timeout 10 --max-time 30 "$url") || code=000
  if [[ "$code" =~ ^($expected)$ ]]; then echo "OK $url -> $code"; else echo "FAIL $url -> $code (ожидалось $expected)"; fail=1; fi
}
check "https://$DOMAIN/" 200
check "https://$DOMAIN/api/health" 200
check "https://$DOMAIN/api/services" 200
check "https://$DOMAIN/docs" 200
check "https://$DOMAIN/admin.html" 200
check "https://$DOMAIN/account.html" 200
check "http://$DOMAIN/" 403
for service in pgadmin registry; do
  if grep -Fxq "$service" <<< "$running"; then echo "FAIL: $service должен быть остановлен"; fail=1; else echo "STOPPED $service"; fi
done
if ss -lntH '( sport = :8000 or sport = :5432 or sport = :5050 or sport = :5000 )' | grep -q .; then
  echo 'FAIL: обнаружен слушающий порт 8000/5432/5050/5000'; fail=1
else echo 'OK: порты backend, PostgreSQL, pgAdmin и Registry не слушаются на хосте'; fi
# Docker can publish ports via NAT without a host listening process.
if ! python3 - <<'PYPORTS'
import json, subprocess
ids=subprocess.check_output(['docker','compose','ps','-q'],text=True).split()
for cid in ids:
    info=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
    service=info['Config']['Labels'].get('com.docker.compose.service','')
    ports=info['NetworkSettings'].get('Ports') or {}
    bound=[p for p,bindings in ports.items() if bindings]
    if service in ('backend','postgres','pgadmin','registry') and bound:
        raise SystemExit('FAIL: Docker публикует порты '+service+': '+','.join(bound))
    if service=='nginx' and any(p not in ('80/tcp','443/tcp') for p in bound):
        raise SystemExit('FAIL: у Nginx есть лишние публикации портов')
print('OK: публикации Docker проверены')
PYPORTS
then fail=1; fi
docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' || fail=1
exit "$fail"
