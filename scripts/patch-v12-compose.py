#!/usr/bin/env python3
import sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.read_text()
if 'logicpulse-backend:1.2.0' in s:
    raise SystemExit('Compose уже версии 1.2.0; повторное обновление не требуется.')
if s.count('image: logicpulse-backend:1.1.2')!=2:
    raise SystemExit('Неожиданная версия Compose. Остановлено без изменений.')
for port in ('5050','5000'):
    line=f'      - "{port}:{port}"\n'
    if s.count(line)!=1: raise SystemExit('Неожиданное объявление порта '+port)
    s=s.replace(line,'')
s=s.replace('image: logicpulse-backend:1.1.2','image: logicpulse-backend:1.2.0')
needle='      ADMIN_API_KEY: ${ADMIN_API_KEY:?Run scripts/prepare-app.sh}'
if s.count(needle)!=1: raise SystemExit('Не найдена настройка backend.')
s=s.replace(needle,needle+'\n      APP_ENV: production\n      APP_ORIGIN: https://${DOMAIN:?Run scripts/init-env.sh}')
for service in ('pgadmin','registry'):
    needle=f'  {service}:\n    <<: *common'
    if s.count(needle)!=1: raise SystemExit('Неожиданная структура '+service)
    s=s.replace(needle,needle+'\n    profiles: [maintenance]'+ ('\n    ports: ["127.0.0.1:5050:80"]' if service=='pgadmin' else ''))
s=s.replace('PGADMIN_CONFIG_SESSION_COOKIE_SECURE: "True"','PGADMIN_CONFIG_SESSION_COOKIE_SECURE: "False"')
p.write_text(s)
