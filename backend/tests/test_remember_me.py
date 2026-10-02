from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

import pytest
from sqlalchemy import select

from test_api import client
from app import auth, manage
from app.models import AuthSession, User

CREDS = {'email': 'remember@example.com', 'password': 'Remember-test-password-123'}


@pytest.mark.parametrize('route', ['register', 'login'])
@pytest.mark.parametrize('remember', [None, False, True])
def test_browser_cookie_and_server_expiry_match(client, monkeypatch, route, remember):
    client.base_url = 'https://testserver'
    if route == 'login':
        assert client.post('/api/auth/register', json=CREDS).status_code == 201
    instant = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(auth, 'now', lambda: instant)
    payload = dict(CREDS)
    if remember is not None:
        payload['remember_me'] = remember
    response = client.post('/api/auth/' + route, json=payload)
    assert response.status_code == (201 if route == 'register' else 200)
    cookie = SimpleCookie(response.headers['set-cookie'])[auth.COOKIE]
    seconds = 2592000 if remember else 43200
    assert int(cookie['max-age']) == seconds
    assert cookie['secure'] and cookie['httponly']
    assert cookie['samesite'] == 'lax' and cookie['path'] == '/'
    with client.test_factory() as db:
        stored = db.get(AuthSession, auth.hash_token(cookie.value))
        assert auth.aware(stored.expires_at) == instant + timedelta(seconds=seconds)
        assert stored.token_hash != cookie.value
    # Restore only the persistent cookie, as when reopening a browser.
    client.cookies.clear()
    client.cookies.set(auth.COOKIE, cookie.value)
    assert client.get('/api/auth/me').status_code == 200
    monkeypatch.setattr(auth, 'now', lambda: instant + timedelta(seconds=seconds - 1))
    assert client.get('/api/auth/me').status_code == 200
    # A read does not silently extend the absolute expiry.
    monkeypatch.setattr(auth, 'now', lambda: instant + timedelta(seconds=seconds))
    assert client.get('/api/auth/me').status_code == 401


def test_remembered_session_csrf_logout_and_cookie_replay(client):
    client.base_url = 'https://testserver'
    response = client.post('/api/auth/register', json={**CREDS, 'remember_me': True})
    cookie = SimpleCookie(response.headers['set-cookie'])[auth.COOKIE].value
    assert client.get('/api/admin/services').status_code == 403
    assert client.post('/api/auth/logout').status_code == 403
    response = client.post('/api/auth/logout', headers={'X-CSRF-Token': response.json()['csrf_token']})
    assert response.status_code == 204
    assert SimpleCookie(response.headers['set-cookie'])[auth.COOKIE]['max-age'] == '0'
    client.cookies.clear()
    client.cookies.set(auth.COOKIE, cookie)
    assert client.get('/api/auth/me').status_code == 401
    with client.test_factory() as db:
        assert db.get(AuthSession, auth.hash_token(cookie)) is None


def test_swagger_tokens_keep_twelve_hour_lifetime(client):
    client.post('/api/auth/register', json={**CREDS, 'remember_me': True})
    response = client.post('/api/auth/token', json=CREDS)
    assert response.status_code == 200
    assert response.json()['expires_in'] == 43200
    assert 'set-cookie' not in response.headers
    with client.test_factory() as db:
        row = db.get(AuthSession, auth.hash_token(response.json()['access_token']))
        assert 43190 < (auth.aware(row.expires_at) - auth.now()).total_seconds() <= 43200
    assert client.post('/api/auth/token', json={**CREDS, 'remember_me': True}).status_code == 422


@pytest.mark.parametrize('value', ['true', 1, None])
def test_remember_me_requires_boolean(client, value):
    assert client.post('/api/auth/register', json={**CREDS, 'remember_me': value}).status_code == 422


def test_admin_password_reset_revokes_remembered_sessions(client, monkeypatch):
    client.base_url = 'https://testserver'
    response = client.post('/api/auth/register', json={**CREDS, 'remember_me': True})
    cookie = SimpleCookie(response.headers['set-cookie'])[auth.COOKIE].value
    with client.test_factory() as db:
        user = db.scalar(select(User))
        user.role = 'admin'
        db.commit()
    monkeypatch.setattr(manage, 'SessionLocal', client.test_factory)
    monkeypatch.setattr('builtins.input', lambda _: CREDS['email'])
    monkeypatch.setattr(manage.getpass, 'getpass', lambda _: 'A-different-new-password-123')
    monkeypatch.setattr('sys.argv', ['manage', 'admin'])
    manage.main()
    client.cookies.clear()
    client.cookies.set(auth.COOKIE, cookie)
    assert client.get('/api/auth/me').status_code == 401
