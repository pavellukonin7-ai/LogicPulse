import os
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['ADMIN_API_KEY'] = 'test-admin-key-' + 'x' * 40

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.database import Base, session
from app.main import app

KEY = {'X-Admin-Key': os.environ['ADMIN_API_KEY']}
SERVICE = dict(slug='web-development', name='Разработка веб-сервисов',
    description='Корпоративные сайты и веб-приложения под задачи компании.',
    price_min=80000, price_max=350000)

@pytest.fixture
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[session] = override
    with TestClient(app) as client:
        client.test_factory = factory
        yield client
    app.dependency_overrides.clear()
    engine.dispose()

def new_service(client, **kwargs):
    result = client.post('/api/services', headers=KEY, json={**SERVICE, **kwargs})
    assert result.status_code == 201, result.text
    return result.json()

def new_request(service_id):
    return dict(request_id=str(uuid4()), service_id=service_id, name='Тестовый клиент',
                email='test@example.com', company='Проверка',
                message='Нужен личный кабинет для обработки заявок клиентов.', consent=True)

def test_admin_operations_require_key(client):
    assert client.post('/api/services', json=SERVICE).status_code == 401
    assert client.get('/api/admin/requests').status_code == 401
    assert client.get('/api/admin/services', headers={'X-Admin-Key': 'wrong'}).status_code == 401

def test_draft_price_not_public_and_get_returns_services(client):
    new_service(client)
    public = client.get('/api/services').json()
    assert len(public) == 1 and public[0]['price_min'] is None
    assert 'price_review_note' not in public[0]
    assert client.get('/api/admin/services', headers=KEY).json()[0]['price_min'] == 80000

def test_price_approval_requires_review_and_publishes_range(client):
    assert client.post('/api/services', headers=KEY, json={**SERVICE, 'prices_approved': True}).status_code == 422
    service = new_service(client)
    result = client.put(f"/api/services/{service['id']}", headers=KEY,
        json={**SERVICE, 'prices_approved': True, 'price_review_note': 'Объём: сайт 5 страниц; 3 недели; оценка затрат согласована.'})
    assert result.status_code == 200
    assert client.get('/api/services').json()[0]['price_max'] == 350000

def test_invalid_ranges_and_duplicate_slug(client):
    assert client.post('/api/services', headers=KEY, json={**SERVICE, 'price_max': 1}).status_code == 422
    assert client.post('/api/services', headers=KEY, json={**SERVICE, 'price_min': -1}).status_code == 422
    new_service(client)
    assert client.post('/api/services', headers=KEY, json=SERVICE).status_code == 409

def test_request_persisted_and_idempotent(client):
    service = new_service(client)
    payload = new_request(service['id'])
    result = client.post('/api/requests', json=payload)
    assert result.status_code == 201
    assert result.json()['message'] == 'Заявка отправлена!'
    assert client.post('/api/requests', json=payload).status_code == 201
    rows = client.get('/api/admin/requests', headers=KEY).json()
    assert len(rows) == 1 and rows[0]['service_id'] == service['id']
    assert rows[0]['email'] == payload['email'] and 'payload_hash' not in rows[0]
    assert client.post('/api/requests', json={**payload, 'name': 'Другой клиент'}).status_code == 409

def test_inactive_or_missing_services_rejected(client):
    service = new_service(client, active=False)
    assert client.get('/api/services').json() == []
    assert client.post('/api/requests', json=new_request(service['id'])).status_code == 422
    assert client.post('/api/requests', json=new_request(999)).status_code == 422

@pytest.mark.parametrize('changes', [dict(consent=False), dict(email='bad'), dict(message='x'), dict(website='spam'), dict(name='  ')])
def test_invalid_requests_not_saved(client, changes):
    service = new_service(client)
    assert client.post('/api/requests', json={**new_request(service['id']), **changes}).status_code == 422
    assert client.get('/api/admin/requests', headers=KEY).json() == []

def test_health_and_swagger_contract(client):
    assert client.get('/api/health').json()['database'] == 'connected'
    assert '/swagger/swagger-ui-bundle.js' in client.get('/docs').text
    schema = client.get('/openapi.json').json()
    assert schema['paths']['/api/services']['post']['security']
    assert client.get('/api/admin/requests', headers=KEY).headers['cache-control'] == 'no-store'

def test_telegram_outbox_is_atomic_and_idempotent(client, monkeypatch):
    from app.models import TelegramDelivery
    from sqlalchemy import select
    monkeypatch.setenv('TELEGRAM_ENABLED', 'true')
    service = new_service(client)
    payload = new_request(service['id'])
    assert client.post('/api/requests', json=payload).status_code == 201
    assert client.post('/api/requests', json=payload).status_code == 201
    assert client.post('/api/requests', json={**payload, 'name': 'Другое имя'}).status_code == 409
    with client.test_factory() as db:
        rows = db.scalars(select(TelegramDelivery)).all()
        assert len(rows) == 1 and rows[0].request_id == payload['request_id']
    assert client.get('/api/admin/telegram').status_code == 401
    assert client.get('/api/admin/telegram', headers=KEY).json()['counts']['pending'] == 1

def test_telegram_disabled_and_no_historical_replay(client, monkeypatch):
    monkeypatch.setenv('TELEGRAM_ENABLED', 'false')
    service = new_service(client)
    payload = new_request(service['id'])
    assert client.post('/api/requests', json=payload).status_code == 201
    monkeypatch.setenv('TELEGRAM_ENABLED', 'true')
    assert client.post('/api/requests', json=payload).status_code == 201
    assert client.get('/api/admin/telegram', headers=KEY).json()['counts']['pending'] == 0

def test_telegram_queue_failure_rolls_back_request(client, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from app.models import TelegramDelivery
    from sqlalchemy import event
    monkeypatch.setenv('TELEGRAM_ENABLED', 'true')
    service = new_service(client)
    payload = new_request(service['id'])
    def fail(*args):
        raise IntegrityError('test', {}, Exception())
    event.listen(TelegramDelivery, 'before_insert', fail)
    try:
        assert client.post('/api/requests', json=payload).status_code == 409
        assert client.get('/api/admin/requests', headers=KEY).json() == []
    finally:
        event.remove(TelegramDelivery, 'before_insert', fail)

def test_delivery_retry_survives_session_restart_and_preserves_request(client, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from app.models import TelegramDelivery
    from app.telegram import TelegramError
    from app.telegram_worker import deliver_one
    monkeypatch.setenv('TELEGRAM_ENABLED', 'true')
    service = new_service(client)
    payload = new_request(service['id'])
    assert client.post('/api/requests', json=payload).status_code == 201
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    def limited(*args):
        raise TelegramError(429, retry_after=120)
    assert deliver_one(client.test_factory, 'unused', '123', limited, now)
    assert not deliver_one(client.test_factory, 'unused', '123', limited, now + timedelta(seconds=119))
    with client.test_factory() as db:
        item = db.get(TelegramDelivery, payload['request_id'])
        assert item.status == 'pending' and item.attempts == 1
    assert deliver_one(client.test_factory, 'unused', '123', lambda *args: 42, now + timedelta(seconds=121))
    assert not deliver_one(client.test_factory, 'unused', '123', lambda *args: 43, now + timedelta(seconds=180))
    with client.test_factory() as db:
        item = db.get(TelegramDelivery, payload['request_id'])
        assert item.status == 'sent' and item.attempts == 2 and item.telegram_message_id == '42'
    assert len(client.get('/api/admin/requests', headers=KEY).json()) == 1

def test_permanent_failure_requires_explicit_admin_retry(client, monkeypatch):
    from app.telegram import TelegramError
    from app.telegram_worker import deliver_one
    monkeypatch.setenv('TELEGRAM_ENABLED', 'true')
    service = new_service(client)
    payload = new_request(service['id'])
    client.post('/api/requests', json=payload)
    def blocked(*args):
        raise TelegramError(403, retryable=False)
    assert deliver_one(client.test_factory, 'unused', '123', blocked)
    url = '/api/admin/telegram/' + payload['request_id'] + '/retry'
    assert client.get('/api/admin/telegram', headers=KEY).json()['counts']['failed'] == 1
    assert client.post(url).status_code == 401
    assert client.post(url, headers=KEY).status_code == 200
    assert client.post(url, headers=KEY).status_code == 409
    assert deliver_one(client.test_factory, 'unused', '123', lambda *args: 50)
