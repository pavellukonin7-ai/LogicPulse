#!/usr/bin/env python3
"""LogicPulse: dedicated Xray client, tested before switching the existing relay.

Imports a private Happ JSON file on the VPS. Never embeds or prints credentials.
No database, application image, .env, SSH or firewall changes.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

ROOT = Path('/opt/logicpulse')
VERSION = 'v26.3.27'  # Explicit release, never an unreviewed latest download.
BASE = 'https://github.com/XTLS/Xray-core/releases/download/' + VERSION
BIN = Path('/usr/local/lib/logicpulse-xray') / VERSION / 'xray'
CONFIG = Path('/etc/logicpulse-xray/config.json')
UNIT = Path('/etc/systemd/system/logicpulse-xray.service')
DROP = Path('/etc/systemd/system/logicpulse-telegram-proxy.service.d/30-server-proxy.conf')
RELAY = 'logicpulse-telegram-proxy.service'
SOCK = 'logicpulse-telegram-proxy.socket'
NATIVE = 'logicpulse-xray.service'
BACKUPS = Path('/root')
RELAY_FILE = Path('/etc/systemd/system') / RELAY
UDS_PROXY = 'socks5h://localhost/run/logicpulse-telegram/proxy.sock'
MARKER = '# Managed by LogicPulse server-proxy v1.1.3'
GETME = '''import os,sys
from app.telegram import call
try:
    assert os.environ.get('TELEGRAM_ENABLED') == 'true'
    assert os.environ.get('BOT_PROXY') == 'socks5h://localhost/run/logicpulse-telegram/proxy.sock'
    assert call(os.environ['TELEGRAM_BOT_TOKEN'], 'getMe')['username'].lower() == 'logicpulseleadsbot'
except Exception:
    sys.exit(1)
print('OK: @LogicPulseLeadsBot доступен из telegram-worker')
'''


def run(args, *, check=True, cwd=None, timeout=60):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('Команда не выполнена: ' + args[0] + ' (код ' + str(result.returncode) + ').')
    return result


def ctl(*args, check=True):
    return run(['systemctl', *args], check=check)


def compose(*args, check=True, timeout=60):
    return run(['docker', 'compose', *args], check=check, cwd=ROOT, timeout=timeout)


def write_file(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.logicpulse-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data if isinstance(data, bytes) else data.encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def build_config(source):
    """Accept precisely the demonstrated Happ VLESS/TCP/TLS export shape."""
    if not isinstance(source, dict):
        raise ValueError('Нужен один JSON-объект конфигурации Happ.')
    choices = [o for o in source.get('outbounds', [])
               if isinstance(o, dict) and o.get('tag') == 'proxy' and o.get('protocol') == 'vless']
    if len(choices) != 1:
        raise ValueError('Нужен один VLESS outbound с тегом proxy.')
    outbound = copy.deepcopy(choices[0])
    stream = outbound.get('streamSettings', {})
    tls = stream.get('tlsSettings', {})
    if stream.get('network') not in ('tcp', 'raw') or stream.get('security') != 'tls':
        raise ValueError('Установщик рассчитан на экспорт VLESS/TCP/TLS. Другой профиль не изменён.')
    if tls.get('allowInsecure') or not tls.get('serverName'):
        raise ValueError('Нужны serverName и включённая проверка TLS.')
    if (outbound.get('proxySettings') or stream.get('sockopt', {}).get('dialerProxy')
            or tls.get('certificates')):
        raise ValueError('Профиль содержит дополнительные зависимости; требуется отдельная проверка.')
    peers = outbound.get('settings', {}).get('vnext', [])
    if len(peers) != 1 or len(peers[0].get('users', [])) != 1:
        raise ValueError('Ожидался один сервер и один пользователь VLESS.')
    peer, user = peers[0], peers[0]['users'][0]
    if not isinstance(peer.get('port'), int) or not 1 <= peer['port'] <= 65535:
        raise ValueError('Некорректный порт VLESS.')
    if not isinstance(peer.get('address'), str) or not peer['address']:
        raise ValueError('Не задан адрес VLESS.')
    try:
        uuid.UUID(user['id'])
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('Некорректный идентификатор пользователя VLESS.') from None
    if user.get('encryption') != 'none' or user.get('flow', '') not in ('', 'xtls-rprx-vision'):
        raise ValueError('Неожиданные параметры VLESS; требуется отдельная проверка.')
    # Keep the provider's endpoint, SNI, ALPN, fingerprint and flow unchanged.
    outbound = {k: outbound[k] for k in ('protocol', 'settings', 'streamSettings')}
    outbound['tag'] = 'provider'
    return {
        'log': {'loglevel': 'warning'},
        'inbounds': [{'tag': 'telegram-socks', 'listen': '127.0.0.1', 'port': 18081,
                      'protocol': 'socks', 'settings': {'auth': 'noauth', 'udp': False}}],
        # Default deny; no direct fallback when the provider is unavailable.
        'outbounds': [{'tag': 'blocked', 'protocol': 'blackhole', 'settings': {}}, outbound],
        'routing': {'domainStrategy': 'AsIs', 'rules': [
            {'type': 'field', 'inboundTag': ['telegram-socks'], 'network': 'tcp',
             'domain': ['full:api.telegram.org'], 'port': '443', 'outboundTag': 'provider'}]},
    }


def service_text():
    return f'''{MARKER}
[Unit]
Description=LogicPulse dedicated Telegram Xray client
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
DynamicUser=yes
LoadCredential=config.json:{CONFIG}
ExecStart={BIN} run -config %d/config.json
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
CapabilityBoundingSet=
UMask=0077

[Install]
WantedBy=multi-user.target
'''


def relay_text():
    executable = next((p for p in ('/usr/lib/systemd/systemd-socket-proxyd',
                                  '/lib/systemd/systemd-socket-proxyd') if os.access(p, os.X_OK)), None)
    if executable is None:
        raise ValueError('Не найден systemd-socket-proxyd.')
    # Wants (rather than Requires) allows the relay to survive an Xray restart.
    return f'''{MARKER}
[Unit]
Description=LogicPulse Telegram socket to server Xray
Wants={NATIVE}
After={NATIVE}

[Service]
ExecStart=
ExecStart={executable} 127.0.0.1:18081
'''


def verify_digest(archive, digest):
    hashes = re.findall(r'(?im)^[^\r\n]*256[^\r\n=]*=\s*([0-9a-f]{64})[ \t]*$', digest)
    if len(hashes) != 1 or hashlib.sha256(archive).hexdigest() != hashes[0].lower():
        raise ValueError('Проверка SHA256 Xray не пройдена. Установка остановлена.')


def download(url, target):
    for proxy in (None, UDS_PROXY):
        options = ['--noproxy', '*'] if proxy is None else ['--proxy', proxy, '--noproxy', '']
        result = run(['curl', '-q', '--fail', '--location', '--silent', '--show-error',
                      '--proto', '=https', '--proto-redir', '=https', '--connect-timeout', '10',
                      '--max-time', '180', *options, '--output', str(target), url],
                     check=False, timeout=190)
        if result.returncode == 0:
            return
        print('Загрузка не удалась; проверяю резервный путь через действующий прокси.', flush=True)
    raise RuntimeError('Не удалось скачать официальный выпуск Xray. Проверьте Windows-туннель и повторите.')


def get_binary(temp):
    machine = {'x86_64': '64', 'aarch64': 'arm64-v8a'}.get(platform.machine())
    if machine is None:
        raise ValueError('Поддерживаются только Linux x86_64 и aarch64.')
    name = 'Xray-linux-' + machine + '.zip'
    archive, digest = temp / name, temp / (name + '.dgst')
    print('Загрузка официального Xray ' + VERSION + ' и проверка SHA256…', flush=True)
    download(BASE + '/' + name, archive)
    download(BASE + '/' + name + '.dgst', digest)
    verify_digest(archive.read_bytes(), digest.read_text())
    with zipfile.ZipFile(archive) as z:
        info = z.getinfo('xray')
        if info.file_size > 200_000_000:
            raise ValueError('Неожиданный размер Xray.')
        binary = z.read(info)
    if not binary.startswith(b'\x7fELF'):
        raise ValueError('Неожиданный формат Xray.')
    path = temp / 'xray'
    write_file(path, binary, 0o700)
    return path


def probe(proxy, *, container=False):
    command = ['curl', '-q', '--proxy', proxy, '--noproxy', '', '--head', '--silent',
               '--show-error', '--output', '/dev/null', '--write-out', '%{http_code}',
               '--connect-timeout', '10', '--max-time', '25', 'https://api.telegram.org/']
    result = compose('exec', '-T', 'telegram-worker', *command, check=False) if container else run(command, check=False)
    if result.returncode or result.stdout.strip() not in ('200', '301', '302', '307', '308'):
        raise RuntimeError('Telegram не ответил через проверяемый прокси. TLS-проверка остаётся включённой.')


def wait_port():
    for _ in range(30):
        try:
            with socket.create_connection(('127.0.0.1', 18081), timeout=0.2):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError('Служба Xray не открыла локальный порт. Проверьте её журнал.')


def check_worker():
    result = compose('ps', '--status', 'running', '--services')
    if 'telegram-worker' not in result.stdout.splitlines():
        raise ValueError('telegram-worker должен быть запущен до установки.')
    # Read only expected flags, never print environment or token.
    code = "import os,sys;sys.exit(0 if os.getenv('BOT_PROXY') == " + repr(UDS_PROXY) + " and os.getenv('TELEGRAM_ENABLED') == 'true' and os.getenv('TELEGRAM_BOT_TOKEN') else 1)"
    compose('exec', '-T', 'telegram-worker', 'python', '-c', code)


def check_bot():
    compose('exec', '-T', 'telegram-worker', 'python', '-c', GETME)
    print('OK: @LogicPulseLeadsBot доступен из telegram-worker', flush=True)


def switch_relay(contents):
    """Pause delivery for the cutover; API continues storing new requests."""
    try:
        compose('stop', '--timeout', '30', 'telegram-worker')
        if contents is None:
            DROP.unlink(missing_ok=True)
        else:
            write_file(DROP, contents, 0o644)
        ctl('daemon-reload')
        ctl('restart', RELAY)
        probe(UDS_PROXY)
    finally:
        compose('start', 'telegram-worker')
    probe(UDS_PROXY, container=True)
    check_bot()


def restore_relay(contents):
    # Best-effort actions are all attempted; never silently claim a failed rollback.
    failures = []
    if contents is None:
        DROP.unlink(missing_ok=True)
    else:
        write_file(DROP, contents, 0o644)
    for action in (lambda: ctl('daemon-reload'), lambda: ctl('restart', RELAY),
                   lambda: compose('start', 'telegram-worker')):
        try:
            action()
        except Exception:
            failures.append(True)
    if failures:
        raise RuntimeError('Автоматический откат не завершён. Нужна проверка systemctl и docker compose ps.')


def rollback():
    if not DROP.exists() or MARKER not in DROP.read_text():
        raise ValueError('Переключение на серверный Xray не найдено.')
    # Confirm the replacement before disconnecting a working server proxy.
    probe('socks5h://127.0.0.1:18080')
    previous = DROP.read_bytes()
    try:
        switch_relay(None)
    except (Exception, KeyboardInterrupt):
        restore_relay(previous)
        raise
    ctl('disable', '--now', NATIVE)
    print('Откат выполнен: снова используется Windows-туннель. Его окно должно оставаться открытым.')


def install(source):
    if DROP.exists():
        raise ValueError('Серверный прокси уже настроен или есть конфликт drop-in. Используйте --check.')
    if UNIT.exists() and MARKER not in UNIT.read_text():
        raise ValueError('Служба logicpulse-xray уже существует и не принадлежит этому установщику.')
    if UNIT.exists() and (ctl('is-active', '--quiet', NATIVE, check=False).returncode == 0
                          or ctl('is-enabled', '--quiet', NATIVE, check=False).returncode == 0):
        raise ValueError('Служба Xray уже запущена или включена. Используйте --check; переустановка остановлена.')
    if CONFIG.exists() and not UNIT.exists():
        raise ValueError('Обнаружен неизвестный config.json; он не будет перезаписан.')
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 1_000_000:
        raise ValueError('Нужен обычный JSON-файл Happ размером до 1 МБ.')
    if source.stat().st_uid != 0 or source.stat().st_mode & 0o077:
        raise ValueError('Файл должен принадлежать root и иметь права 600: chmod 600 /root/logicpulse-happ.json')
    config = build_config(json.loads(source.read_text(encoding='utf-8-sig')))
    with socket.socket() as test:
        try:
            test.bind(('127.0.0.1', 18081))
        except OSError:
            raise ValueError('Порт 18081 занят. Существующая служба не изменена.') from None
    override = relay_text()
    with tempfile.TemporaryDirectory(prefix='logicpulse-xray-') as directory:
        temp = Path(directory)
        binary = get_binary(temp)
        candidate = temp / 'config.json'
        write_file(candidate, json.dumps(config, ensure_ascii=False, indent=2) + '\n')
        result = run([str(binary), 'run', '-test', '-config', str(candidate)], check=False)
        if result.returncode:
            raise ValueError('Xray не принял конфигурацию; действующий прокси не изменён.')
        backup = BACKUPS / ('logicpulse-proxy-before-' + str(time.time_ns()))
        backup.mkdir(mode=0o700)
        tracked = (UNIT, CONFIG)
        originals = {p: p.read_bytes() if p.exists() else None for p in tracked}
        for path, data in originals.items():
            if data is not None:
                write_file(backup / path.name, data)
        write_file(backup / 'relay.service', RELAY_FILE.read_bytes())
        touched = False
        try:
            BIN.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(BIN.parent.parent, 0o755)
            os.chmod(BIN.parent, 0o755)
            write_file(BIN, binary.read_bytes(), 0o755)
            CONFIG.parent.mkdir(exist_ok=True)
            os.chmod(CONFIG.parent, 0o700)
            write_file(CONFIG, candidate.read_bytes())
            write_file(UNIT, service_text(), 0o644)
            ctl('daemon-reload')
            ctl('start', NATIVE)
            wait_port()
            probe('socks5h://127.0.0.1:18081')
            print('OK: Telegram доступен через серверный Xray. Переключаю отправку…', flush=True)
            touched = True
            switch_relay(override)
            ctl('enable', NATIVE, SOCK)
            print('Готово: Telegram использует серверный Xray. Автозапуск включён.')
            print('Резервная копия настроек: ' + str(backup))
            print('Закройте Windows SSH-туннель и отправьте НОВУЮ тестовую заявку с сайта.')
        except (Exception, KeyboardInterrupt):
            recovery_error = None
            if touched:
                try:
                    restore_relay(None)
                except Exception as exc:
                    recovery_error = exc
            ctl('disable', '--now', NATIVE, check=False)
            for path, data in originals.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    write_file(path, data, 0o644 if path == UNIT else 0o600)
            ctl('daemon-reload', check=False)
            if recovery_error:
                raise recovery_error
            print('Настройки прежнего прокси сохранены/восстановлены. Для его работы нужен Windows-туннель.')
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--config', type=Path)
    actions.add_argument('--check', action='store_true')
    actions.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0 or not (ROOT / '.env').is_file():
        raise ValueError('Нужен root на сервере с установленным /opt/logicpulse.')
    os.umask(0o077)
    for executable in ('curl', 'systemctl', 'docker'):
        if not shutil.which(executable):
            raise ValueError('Не найдена команда: ' + executable)
    for suffix in ('service', 'socket'):
        if not (Path('/etc/systemd/system') / ('logicpulse-telegram-proxy.' + suffix)).is_file():
            raise ValueError('Сначала нужна действующая настройка приватного Unix-прокси v1.1.2.')
    with open('/run/lock/logicpulse-server-proxy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_worker()
        ctl('is-active', '--quiet', SOCK)
        if args.rollback:
            rollback()
        elif args.check:
            if not DROP.exists() or MARKER not in DROP.read_text():
                raise ValueError('Серверный прокси ещё не установлен.')
            ctl('is-active', '--quiet', NATIVE)
            ctl('is-enabled', '--quiet', NATIVE)
            probe('socks5h://127.0.0.1:18081')
            probe(UDS_PROXY, container=True)
            check_bot()
            print('OK: серверный прокси и доступ бота работают; автозапуск включён.')
        else:
            install(args.config)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit('Настройка прервана.')
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc))
    except Exception as exc:
        raise SystemExit('Настройка остановлена (' + type(exc).__name__ + '). Конфигурацию и токены не присылайте.')
