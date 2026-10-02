#!/usr/bin/env python3
"""Conservative additive edit of the known v1.1 compose, preserving other services."""
from pathlib import Path
import sys

WORKER = '''  telegram-worker:
    <<: *common
    image: logicpulse-backend:1.1.2
    command: [python, -m, app.telegram_worker]
    volumes:
      - /run/logicpulse-telegram:/run/logicpulse-telegram:ro
    stop_grace_period: 30s
    environment:
      POSTGRES_DB: ${POSTGRES_DB:?Run scripts/init-env.sh}
      POSTGRES_USER: ${POSTGRES_USER:?Run scripts/init-env.sh}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Run scripts/init-env.sh}
      DB_HOST: db
      TELEGRAM_ENABLED: ${TELEGRAM_ENABLED:-false}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}
      TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID:-}
      BOT_PROXY: ${BOT_PROXY:-}
    depends_on:
      backend:
        condition: service_healthy
    networks: [frontend, database]
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    healthcheck:
      test: [CMD, python, -c, "import os,time; assert time.time()-os.stat('/tmp/telegram-worker.heartbeat').st_mtime < 90"]
      interval: 20s
      timeout: 5s
      retries: 3
      start_period: 20s
    labels:
      com.centurylinklabs.watchtower.enable: "false"
'''


def patch(data):
    if '  telegram-worker:\n' in data:
        if 'image: logicpulse-backend:1.1.1' in data:
            data = data.replace('image: logicpulse-backend:1.1.1', 'image: logicpulse-backend:1.1.2')
        elif 'image: logicpulse-backend:1.1.2' not in data:
            raise ValueError('Неожиданная версия telegram-worker; изменение остановлено.')
        start = data.index('  telegram-worker:\n')
        end = data.index('\n  postgres:\n', start)
        worker = data[start:end]
        if '      BOT_PROXY:' not in worker:
            worker = worker.replace('      TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID:-}\n',
                '      TELEGRAM_CHAT_ID: ${TELEGRAM_CHAT_ID:-}\n      BOT_PROXY: ${BOT_PROXY:-}\n')
        if '    volumes:' not in worker:
            worker = worker.replace('    command: [python, -m, app.telegram_worker]\n',
                '    command: [python, -m, app.telegram_worker]\n    volumes:\n      - /run/logicpulse-telegram:/run/logicpulse-telegram:ro\n')
        elif '/run/logicpulse-telegram:/run/logicpulse-telegram:ro' not in worker:
            raise ValueError('У worker нестандартные volumes; проверьте Compose вручную.')
        return data[:start] + worker + data[end:]
    anchor = '    build: ./backend\n'
    env = '      ADMIN_API_KEY: ${ADMIN_API_KEY:?Run scripts/prepare-app.sh}\n'
    if data.count(anchor) != 1 or data.count(env) != 1 or data.count('\n  postgres:\n') != 1:
        raise ValueError('Compose отличается от v1.1: обновление остановлено до изменения файлов.')
    data = data.replace(anchor, anchor + '    image: logicpulse-backend:1.1.2\n', 1)
    data = data.replace(env, env + '      TELEGRAM_ENABLED: ${TELEGRAM_ENABLED:-false}\n', 1)
    return data.replace('\n  postgres:\n', '\n' + WORKER + '  postgres:\n', 1)


if __name__ == '__main__':
    try:
        src, dst = map(Path, sys.argv[1:])
        dst.write_text(patch(src.read_text()))
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
