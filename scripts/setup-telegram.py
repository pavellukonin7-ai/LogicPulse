#!/usr/bin/env python3
"""Run on the VPS with python3. Token is read from TTY, never command arguments."""
import getpass
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.telegram import call, TelegramError, normalize_proxy


def load_proxy(path):
    values = [line.split('=', 1)[1].strip() for line in path.read_text().splitlines()
              if line.strip().startswith('BOT_PROXY=')]
    if len(values) > 1:
        raise ValueError('В .env есть повторяющиеся BOT_PROXY. Устраните дубликаты.')
    if 'BOT_PROXY' not in os.environ and values:
        value = values[0]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ['BOT_PROXY'] = value
    proxy = normalize_proxy(os.environ.get('BOT_PROXY', '').strip())
    if proxy:
        os.environ['BOT_PROXY'] = proxy
        print('Подключение к Telegram через настроенный прокси (адрес скрыт).')


def write_settings(path, values):
    original = path.read_text()
    lines = original.splitlines()
    found = set()
    output = []
    for line in lines:
        key = line.partition('=')[0].strip()
        if key in values:
            if key in found:
                raise ValueError('В .env есть повторяющиеся настройки Telegram. Устраните дубликаты.')
            found.add(key)
            output.append(f'{key}={values[key]}')
        else:
            output.append(line)
    output.extend(f'{key}={value}' for key, value in values.items() if key not in found)
    backup = path.with_name('.env.before-telegram-' + str(time.time_ns()))
    # Exclusive creation avoids ever replacing an older backup.
    with backup.open('x') as target:
        os.chmod(backup, 0o600)
        target.write(original)
    fd, temporary = tempfile.mkstemp(prefix='.env.telegram-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as target:
            target.write('\n'.join(output) + '\n')
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    if os.geteuid() != 0 or ROOT != Path('/opt/logicpulse'):
        raise ValueError('Запустите на сервере: python3 /opt/logicpulse/scripts/setup-telegram.py')
    if not sys.stdin.isatty():
        raise ValueError('Нужен интерактивный SSH-терминал для скрытого ввода токена.')
    if not (ROOT / '.env').is_file():
        raise ValueError('Не найден .env действующего проекта.')
    os.umask(0o077)
    load_proxy(ROOT / '.env')
    token = getpass.getpass('Вставьте токен @LogicPulseLeadsBot (ввод скрыт): ').strip()
    bot = call(token, 'getMe')
    if not bot or bot.get('username', '').lower() != 'logicpulseleadsbot':
        raise ValueError('Этот токен принадлежит другому боту. Нужен @LogicPulseLeadsBot.')
    if call(token, 'getWebhookInfo').get('url'):
        raise ValueError('У бота уже установлен webhook. Настройки не изменены; сначала проверьте, где используется бот.')
    print('Проверен бот @LogicPulseLeadsBot.')
    nonce = '/connect_' + secrets.token_hex(12)
    started = int(time.time())
    print('\nОткройте https://t.me/LogicPulseLeadsBot и отправьте ему в ЛИЧНОМ чате команду:')
    print(nonce)
    print('Эта команда привяжет уведомления к вашему чату. Не отправляйте её в группы.')
    offset = None
    chat = None
    while chat is None:
        input('\nПосле отправки команды нажмите Enter здесь (Ctrl+C — отмена): ')
        for _ in range(10):
            payload = {'timeout': 0, 'limit': 100, 'allowed_updates': ['message']}
            if offset is not None:
                payload['offset'] = offset
            updates = call(token, 'getUpdates', payload)
            if not isinstance(updates, list):
                raise ValueError('Неожиданный ответ Telegram. Настройки не изменены.')
            for update in updates:
                offset = update['update_id'] + 1
                message = update.get('message', {})
                candidate = message.get('chat', {})
                if (message.get('text') == nonce and candidate.get('type') == 'private'
                        and message.get('date', 0) >= started):
                    chat = candidate
                    break
            if chat or len(updates) < 100:
                break
        if chat is None:
            print('Команда пока не найдена. Проверьте имя бота и отправьте команду целиком.')
    chat_id = str(chat['id'])
    if not chat_id.isdigit() or int(chat_id) <= 0:
        raise ValueError('Ожидался личный чат Telegram.')
    print(f'Найден личный чат: {chat.get("first_name", "")} (@{chat.get("username", "без username")}).')
    call(token, 'sendMessage', {'chat_id': chat_id,
        'text': 'LogicPulse | Заявки\n\nПроверка связи прошла. Сервер сейчас включает уведомления. После завершения настройки отправьте тестовую заявку с сайта logicpulse.ru.',
        'link_preview_options': {'is_disabled': True}})
    write_settings(ROOT / '.env', {'TELEGRAM_ENABLED': 'true', 'TELEGRAM_BOT_TOKEN': token,
                                  'TELEGRAM_CHAT_ID': chat_id})
    # Only a sanitized worker summary is printed; compose config output is never shown.
    subprocess.run(['docker', 'compose', 'config', '--quiet'], cwd=ROOT, check=True)
    subprocess.run(['docker', 'compose', 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '150',
                    'backend', 'telegram-worker'], cwd=ROOT, check=True)
    print('\nTelegram включён. Теперь отправьте новую тестовую заявку на https://logicpulse.ru/.')
    print('Проверка: docker compose logs --tail=30 telegram-worker')
    print('Исторические заявки повторно не отправляются. Токен сохранён в .env с правами 600.')


if __name__ == '__main__':
    try:
        main()
    except TelegramError as exc:
        messages = {'network': 'Нет соединения с api.telegram.org:443. Проверьте доступ с сервера.',
                    'proxy_network': 'Нет связи через прокси. Проверьте Windows-прокси и открытый SSH-туннель.',
                    'proxy_tls': 'Ошибка проверки TLS через прокси. Проверку сертификатов не отключайте.',
                    'invalid_proxy': 'Некорректный BOT_PROXY. Нужен URL socks5h://, socks5://, http:// или https://.',
                    'curl_missing': 'Не найден curl. Установите на VPS: apt-get install -y curl ca-certificates',
                    '401': 'Telegram отклонил токен. Проверьте токен в BotFather.',
                    '403': 'Откройте бота, разблокируйте его и нажмите Start.',
                    '409': 'Этот бот уже получает обновления в другом приложении.',
                    '429': 'Telegram ограничил частоту запросов. Повторите настройку позже.'}
        print(messages.get(exc.code, f'Ошибка Telegram: {exc.code}. Настройка не завершена.'), file=sys.stderr)
        raise SystemExit(1)
    except (KeyboardInterrupt, EOFError):
        print('\nНастройка прервана.')
        raise SystemExit(1)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    except subprocess.CalledProcessError:
        print('Настройки сохранены, но запуск контейнеров не завершён. Пришлите вывод docker compose ps; .env не присылайте.', file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f'Настройка остановлена ({type(exc).__name__}). Токен и .env не присылайте.', file=sys.stderr)
        raise SystemExit(1)
