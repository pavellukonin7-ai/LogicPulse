"""Small Bot API client. Errors never include token-bearing URLs or API bodies."""
import json
import os
import subprocess
from http.client import HTTPException
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit


class TelegramError(Exception):
    def __init__(self, code='network', *, retryable=True, retry_after=0):
        self.code = str(code)
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__(f'telegram_{self.code}')


def validate_token(token):
    return bool(re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}', token))


def normalize_proxy(value):
    if not value:
        return ''
    try:
        if any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ValueError()
        parts = urlsplit(value)
        if parts.scheme not in ('socks5', 'socks5h', 'http', 'https') or not parts.hostname:
            raise ValueError()
        if parts.fragment or parts.query:
            raise ValueError()
        if parts.path not in ('', '/') and not (parts.hostname == 'localhost' and parts.scheme.startswith('socks5')):
            raise ValueError()
        _ = parts.port  # Validate numeric port.
        if parts.scheme == 'socks5':
            parts = parts._replace(scheme='socks5h')
        return urlunsplit(parts)
    except ValueError:
        raise TelegramError('invalid_proxy', retryable=False) from None


def proxy_request(url, payload, proxy):
    # Sensitive URL, proxy credentials and message body travel on stdin only.
    # No shell, temporary file, verbose curl log or disabled certificate checks.
    options = [('url', url), ('proxy', normalize_proxy(proxy)), ('noproxy', ''),
               ('request', 'POST'), ('header', 'Content-Type: application/json'),
               ('data-binary', json.dumps(payload or {}, ensure_ascii=True)),
               ('connect-timeout', '10'), ('max-time', '20'), ('max-filesize', '2000000'),
               ('proto', '=https'), ('write-out', '\n%{http_code}')]
    config = 'silent\n' + '\n'.join(key + ' = ' + json.dumps(value) for key, value in options) + '\n'
    try:
        result = subprocess.run(['curl', '-q', '--config', '-'], input=config.encode(),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=25, check=False)
    except FileNotFoundError:
        raise TelegramError('curl_missing', retryable=False) from None
    except (OSError, subprocess.TimeoutExpired):
        raise TelegramError('proxy_network') from None
    if result.returncode:
        code = 'proxy_tls' if result.returncode in (51, 60, 77) else 'proxy_network'
        raise TelegramError(code) from None
    body, sep, status = result.stdout.rpartition(b'\n')
    if not sep or not status.isdigit():
        raise TelegramError('invalid_response')
    return int(status), body


def direct_request(url, payload):
    request = urllib.request.Request(url, data=json.dumps(payload or {}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    status = 200
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read(2_000_000)
        exc.close()
    except (OSError, ValueError, HTTPException):
        raise TelegramError('network') from None
    return status, body


def call(token, method, payload=None):
    if not validate_token(token):
        raise TelegramError('invalid_token', retryable=False)
    if not re.fullmatch(r'[A-Za-z]+', method):
        raise TelegramError('invalid_method', retryable=False)
    url = f'https://api.telegram.org/bot{token}/{method}'
    proxy = normalize_proxy(os.getenv('BOT_PROXY', '').strip())
    status, body = proxy_request(url, payload, proxy) if proxy else direct_request(url, payload)
    try:
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise TelegramError('invalid_response') from None
    if status != 200 or not result.get('ok'):
        code = result.get('error_code', status)
        retry_after = result.get('parameters', {}).get('retry_after', 0)
        if not isinstance(retry_after, int) or retry_after < 0:
            retry_after = 0
        raise TelegramError(code, retryable=code == 429 or isinstance(code, int) and code >= 500,
                            retry_after=retry_after)
    return result.get('result')


def truncate(text, units):
    """Limit UTF-16 units, including astral emoji, without splitting a character."""
    return text.encode('utf-16-le')[:units * 2].decode('utf-16-le', errors='ignore')


def notification_text(row):
    from datetime import timezone, timedelta
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    created = created.astimezone(timezone(timedelta(hours=3)))
    heading = (f'LogicPulse | Новая заявка\n\n'
               f'Номер: {row.id}\n'
               f'Получена: {created:%d.%m.%Y %H:%M} МСК\n'
               f'Услуга: {row.service_name}\n'
               f'Имя: {row.name}\n'
               f'Email: {row.email}\n'
               f'Компания: {row.company or "—"}\n\nЗадача:\n')
    message = truncate(row.message, 2300)
    if message != row.message:
        message += '\n[Текст сокращён; полностью — в панели заявок.]'
    return truncate(heading + message, 3800)


def send_notification(token, chat_id, row):
    result = call(token, 'sendMessage', {
        'chat_id': chat_id, 'text': notification_text(row),
        'link_preview_options': {'is_disabled': True}, 'protect_content': True})
    if not isinstance(result, dict) or not isinstance(result.get('message_id'), int):
        raise TelegramError('invalid_response')
    return result['message_id']
