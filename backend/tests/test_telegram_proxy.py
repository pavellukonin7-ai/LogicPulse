import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import threading
from types import SimpleNamespace
import pytest
from app import telegram

TOKEN = '123456:' + 'A' * 35


def test_proxy_stdin_keeps_credentials_out_of_argv(monkeypatch):
    monkeypatch.setenv('BOT_PROXY', 'socks5://user:secret@127.0.0.1:18080')
    def run(args, **kwargs):
        assert args == ['curl', '-q', '--config', '-']
        config = kwargs['input'].decode()
        assert TOKEN in config and 'socks5h://user:secret@127.0.0.1:18080' in config
        assert 'insecure' not in config
        assert kwargs['stderr'] == subprocess.DEVNULL
        assert kwargs['timeout'] == 25
        return SimpleNamespace(returncode=0, stdout=b'{"ok":true,"result":{"id":1}}\n200')
    monkeypatch.setattr(telegram.subprocess, 'run', run)
    assert telegram.call(TOKEN, 'getMe') == {'id': 1}


@pytest.mark.parametrize('proxy', ['file:///tmp/secret', 'socks5h://', 'http://x\nurl=https://bad', 'http://x:bad', 'https://x/a'])
def test_invalid_proxy_is_sanitized(proxy):
    with pytest.raises(telegram.TelegramError) as error:
        telegram.normalize_proxy(proxy)
    assert str(error.value) == 'telegram_invalid_proxy'


@pytest.mark.parametrize('code,reason', [(7, 'proxy_network'), (28, 'proxy_network'), (60, 'proxy_tls')])
def test_curl_failures_safe_for_retry(monkeypatch, code, reason):
    monkeypatch.setenv('BOT_PROXY', 'socks5h://127.0.0.1:18080')
    monkeypatch.setattr(telegram.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=code, stdout=b''))
    with pytest.raises(telegram.TelegramError) as error:
        telegram.call(TOKEN, 'getMe')
    assert error.value.code == reason and error.value.retryable


def test_real_curl_socks_unix_tls_and_json(tmp_path, monkeypatch):
    """Real curl -> local SOCKS5 UDS -> local TLS Bot API fixture, no Internet.

The fixture certificate is explicitly trusted for this test. Production retains
normal CA verification. Also catches curl config quoting/Unicode regressions.
"""
    cert, key = tmp_path / 'ca.pem', tmp_path / 'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
        '-subj', '/CN=api.telegram.org', '-addext', 'subjectAltName=DNS:api.telegram.org',
        '-days', '1', '-keyout', str(key), '-out', str(cert)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Short path required by AF_UNIX even when pytest temp directories are long.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='lp-socks-') as folder:
        path = str(Path(folder) / 'p.sock')
        try:
            listener = socket.socket(socket.AF_UNIX)
        except PermissionError:
            pytest.skip('Runtime forbids AF_UNIX sockets; run this integration test on Linux/VPS')
        listener.bind(path)
        listener.listen(1)
        listener.settimeout(10)
        received, errors = [], []
        def recv_exact(conn, length):
            output = b''
            while len(output) < length:
                chunk = conn.recv(length - len(output))
                if not chunk:
                    raise RuntimeError('unexpected EOF')
                output += chunk
            return output
        def serve():
            try:
                with listener.accept()[0] as conn:
                    conn.settimeout(10)
                    version, methods = recv_exact(conn, 2)
                    assert version == 5
                    recv_exact(conn, methods)
                    conn.sendall(b'\x05\x00')
                    assert recv_exact(conn, 4) == b'\x05\x01\x00\x03'
                    size = recv_exact(conn, 1)[0]
                    assert recv_exact(conn, size) == b'api.telegram.org'
                    assert recv_exact(conn, 2) == b'\x01\xbb'
                    conn.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x01\xbb')
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    context.load_cert_chain(cert, key)
                    with context.wrap_socket(conn, server_side=True) as tls:
                        stream = tls.makefile('rb')
                        assert stream.readline().startswith(b'POST /bot')
                        headers = {}
                        while True:
                            line = stream.readline()
                            if line == b'\r\n': break
                            name, value = line.decode().split(':', 1)
                            headers[name.lower()] = value.strip()
                        received.append(json.loads(stream.read(int(headers['content-length']))))
                        body = b'{"ok":true,"result":{"message_id":123}}'
                        tls.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '
                            + str(len(body)).encode() + b'\r\nConnection: close\r\n\r\n' + body)
                        stream.close()
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        monkeypatch.setenv('BOT_PROXY', 'socks5h://localhost' + path)
        monkeypatch.setenv('CURL_CA_BUNDLE', str(cert))
        payload = {'chat_id': '123', 'text': 'Заявка 😀 "кавычки"\nстрока\\путь\tтаб'}
        try:
            assert telegram.call(TOKEN, 'sendMessage', payload) == {'message_id': 123}
        finally:
            listener.close()
            thread.join(timeout=12)
        assert not errors
        assert received == [payload]
