#!/usr/bin/env python3
"""Expose the existing localhost SSH tunnel to the worker through a private UDS.

No GatewayPorts, public listener, firewall or sshd configuration is changed.
"""
import importlib.util
import os
import pwd
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOCKET_PATH = Path('/run/logicpulse-telegram/proxy.sock')


def ensure_socket_user():
    """systemd resolves numeric SocketUser through host NSS, not container passwd."""
    name, uid = 'logicpulse-notify', 10001
    try:
        by_name = pwd.getpwnam(name)
    except KeyError:
        by_name = None
    try:
        by_uid = pwd.getpwuid(uid)
    except KeyError:
        by_uid = None
    if by_name is not None and by_name.pw_uid != uid:
        raise ValueError('logicpulse-notify уже имеет другой UID; учётные записи не изменены.')
    if by_uid is not None and by_uid.pw_name != name:
        raise ValueError('UID 10001 занят другой учётной записью; учётные записи не изменены.')
    if by_name is None:
        subprocess.run(['useradd', '--uid', str(uid), '--no-create-home',
                        '--home-dir', '/nonexistent', '--shell', '/usr/sbin/nologin', name], check=True)


def units(executable):
    socket = '''[Unit]
Description=LogicPulse Telegram private proxy socket

[Socket]
ListenStream=/run/logicpulse-telegram/proxy.sock
SocketUser=10001
SocketMode=0600
DirectoryMode=0755
RemoveOnStop=yes

[Install]
WantedBy=sockets.target
'''
    service = f'''[Unit]
Description=LogicPulse Telegram socket to Windows SSH tunnel
Requires=logicpulse-telegram-proxy.socket
After=logicpulse-telegram-proxy.socket

[Service]
ExecStart={executable} 127.0.0.1:18080
DynamicUser=yes
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
Restart=on-failure
RestartSec=3
'''
    return socket, service


def main():
    if os.geteuid() != 0 or ROOT != Path('/opt/logicpulse'):
        raise ValueError('Запустите на сервере: python3 /opt/logicpulse/scripts/enable-windows-proxy.py')
    os.umask(0o077)
    # This request contains no token. The SSH forward must already exist.
    subprocess.run(['curl', '-q', '--socks5-hostname', '127.0.0.1:18080',
        '--noproxy', '', '--head', '--silent', '--show-error', '--output', '/dev/null',
        '--connect-timeout', '10', '--max-time', '20', 'https://api.telegram.org/'], check=True)
    executable = next((p for p in ('/usr/lib/systemd/systemd-socket-proxyd',
                                  '/lib/systemd/systemd-socket-proxyd') if os.access(p, os.X_OK)), None)
    if executable is None:
        raise ValueError('Не найден systemd-socket-proxyd. Изменения не выполнены.')
    ensure_socket_user()
    spec = importlib.util.spec_from_file_location('telegram_setup', ROOT / 'scripts/setup-telegram.py')
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    SOCKET_PATH.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    os.chmod(SOCKET_PATH.parent, 0o755)
    for suffix, contents in zip(('socket', 'service'), units(executable)):
        path = Path('/etc/systemd/system') / ('logicpulse-telegram-proxy.' + suffix)
        if path.exists():
            backup = Path('/root') / (path.name + '.before-' + str(time.time_ns()))
            backup.write_bytes(path.read_bytes())
            os.chmod(backup, 0o600)
        path.write_text(contents)
        os.chmod(path, 0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    # Stop the previous consumer before replacing the listening socket.
    subprocess.run(['systemctl', 'stop', 'logicpulse-telegram-proxy.service'], check=True)
    subprocess.run(['systemctl', 'enable', 'logicpulse-telegram-proxy.socket'], check=True)
    subprocess.run(['systemctl', 'restart', 'logicpulse-telegram-proxy.socket'], check=True)
    subprocess.run(['systemctl', 'is-active', '--quiet', 'logicpulse-telegram-proxy.socket'], check=True)
    # Actual curl check under the container UID, using the mounted socket.
    compose = ['docker', 'compose']
    subprocess.run(compose + ['exec', '-T', 'telegram-worker', 'curl', '-q',
        '--proxy', 'socks5h://localhost/run/logicpulse-telegram/proxy.sock', '--noproxy', '',
        '--head', '--silent', '--show-error', '--output', '/dev/null',
        '--write-out', 'Telegram из контейнера: HTTP %{http_code}\n',
        '--connect-timeout', '10', '--max-time', '20', 'https://api.telegram.org/'], cwd=ROOT, check=True)
    setup.write_settings(ROOT / '.env', {'BOT_PROXY': 'socks5h://localhost/run/logicpulse-telegram/proxy.sock'})
    subprocess.run(compose + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '150', 'telegram-worker'],
                   cwd=ROOT, check=True)
    print('Прокси подключён. Следующая команда: python3 scripts/setup-telegram.py')
    print('Оставьте Windows-прокси и окно SSH-туннеля включёнными.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError:
        print('Проверка или настройка остановлена. Пришлите вывод выше; токен не нужен.', file=sys.stderr)
        raise SystemExit(1)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('Настройка прервана.')
    except Exception as exc:
        raise SystemExit(f'Ошибка настройки: {type(exc).__name__}. Токен и .env не присылайте.')
