import pytest
from sqlalchemy import select
from test_api import client, SERVICE, KEY, new_request
from app.models import Service, ServiceDetails

DETAILS = dict(scope_items=['До 7 страниц', 'Форма заявки'], delivery_time='3–5 недель',
               public_note='AI и хостинг отдельно.', button_text='Обсудить сайт')


def test_card_details_crud_and_private_price_review(client):
    payload = {**SERVICE, **DETAILS, 'prices_approved': True,
               'price_review_note': 'Приватная калькуляция: 50 часов разработки и тестирования.'}
    response = client.post('/api/services', json=payload, headers=KEY)
    assert response.status_code == 201, response.text
    sid = response.json()['id']
    for path in ['/api/services', f'/api/services/{sid}', '/api/admin/services']:
        data = client.get(path, headers=KEY).json()
        card = data[0] if isinstance(data, list) else data
        for key, value in DETAILS.items():
            assert card[key] == value
        if '/admin/' not in path:
            assert card['price_min'] == SERVICE['price_min']
            assert 'price_review_note' not in card
            assert 'Приватная калькуляция' not in str(card)
    # Old clients do not erase presentation data by omitting the new fields.
    assert client.put(f'/api/services/{sid}', json={**SERVICE, 'name': 'Изменённое название'}, headers=KEY).status_code == 200
    card = client.get(f'/api/services/{sid}').json()
    assert card['scope_items'] == DETAILS['scope_items']
    assert card['price_min'] is None  # The update has not approved the price.
    changed = {**SERVICE, **DETAILS, 'scope_items': [], 'delivery_time': '', 'public_note': ''}
    assert client.put(f'/api/services/{sid}', json=changed, headers=KEY).status_code == 200
    assert client.get(f'/api/services/{sid}').json()['scope_items'] == []
    request_id = client.post('/api/requests', json=new_request(sid)).json()['id']
    assert client.delete(f'/api/services/{sid}', headers=KEY).status_code == 204
    assert client.get('/api/services').json() == []
    assert client.get('/api/admin/requests/' + request_id, headers=KEY).status_code == 200


def test_legacy_service_without_details_is_readable(client):
    with client.test_factory() as db:
        row = Service(**SERVICE)
        db.add(row)
        db.commit()
        sid = row.id
        assert db.scalar(select(ServiceDetails)) is None
    card = client.get('/api/services').json()[0]
    assert card['scope_items'] == [] and card['delivery_time'] == ''
    assert card['button_text'] == 'Обсудить проект'
    assert client.put(f'/api/services/{sid}', json={**SERVICE, **DETAILS}, headers=KEY).status_code == 200
    assert client.get('/api/services').json()[0]['delivery_time'] == '3–5 недель'


@pytest.mark.parametrize('changes', [
    {'scope_items': ['x'] * 13}, {'scope_items': ['x' * 241]},
    {'scope_items': ['   ']}, {'delivery_time': 'x' * 81},
    {'public_note': 'x' * 1001}, {'button_text': ''},
])
def test_card_input_limits(client, changes):
    assert client.post('/api/services', json={**SERVICE, **changes}, headers=KEY).status_code == 422


def test_public_cannot_write_details(client):
    assert client.post('/api/services', json={**SERVICE, **DETAILS}).status_code == 401
