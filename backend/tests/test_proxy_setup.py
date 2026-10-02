import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

spec = importlib.util.spec_from_file_location('proxy_setup',
    Path(__file__).resolve().parents[2] / 'scripts/enable-windows-proxy.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def absent(*args):
    raise KeyError()


def test_create_host_uid_without_login_or_home(monkeypatch):
    monkeypatch.setattr(setup.pwd, 'getpwnam', absent)
    monkeypatch.setattr(setup.pwd, 'getpwuid', absent)
    calls = []
    monkeypatch.setattr(setup.subprocess, 'run', lambda args, **kw: calls.append(args))
    setup.ensure_socket_user()
    assert calls == [['useradd', '--uid', '10001', '--no-create-home', '--home-dir',
                      '/nonexistent', '--shell', '/usr/sbin/nologin', 'logicpulse-notify']]


def test_existing_correct_user_is_not_changed(monkeypatch):
    user = SimpleNamespace(pw_uid=10001, pw_name='logicpulse-notify')
    monkeypatch.setattr(setup.pwd, 'getpwnam', lambda _: user)
    monkeypatch.setattr(setup.pwd, 'getpwuid', lambda _: user)
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **kw: pytest.fail('unexpected mutation'))
    setup.ensure_socket_user()


@pytest.mark.parametrize('user', [SimpleNamespace(pw_uid=10002, pw_name='logicpulse-notify'),
                                  SimpleNamespace(pw_uid=10001, pw_name='someone-else')])
def test_conflicting_account_is_not_modified(monkeypatch, user):
    monkeypatch.setattr(setup.pwd, 'getpwnam', lambda _: user)
    monkeypatch.setattr(setup.pwd, 'getpwuid', lambda _: user)
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **kw: pytest.fail('unexpected mutation'))
    with pytest.raises(ValueError):
        setup.ensure_socket_user()
