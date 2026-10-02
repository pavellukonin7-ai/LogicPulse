from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
import json
import urllib.error
import pytest
from app import telegram

TOKEN = '123456:' + 'A' * 35


def test_message_length_emoji_and_plain_text(monkeypatch):
    row = SimpleNamespace(id='x' * 36, service_name='😀' * 160, name='<b>Name</b>' * 8,
        email='a' * 240, company='😀' * 160, message='😀' * 4000,
        created_at=datetime.now(timezone.utc))
    sent = {}
    def capture(token, method, payload):
        sent.update(payload)
        return {'message_id': 1}
    monkeypatch.setattr(telegram, 'call', capture)
    assert telegram.send_notification(TOKEN, '123', row) == 1
    assert len(sent['text'].encode('utf-16-le')) // 2 <= 3800
    assert 'parse_mode' not in sent and sent['link_preview_options']['is_disabled']
    assert row.id in sent['text']


@pytest.mark.parametrize('code,retryable', [(400, False), (401, False), (403, False), (429, True), (500, True)])
def test_http_error_sanitized_and_classified(monkeypatch, code, retryable):
    def fail(request, **kwargs):
        assert kwargs['timeout'] == 15
        body = json.dumps({'ok': False, 'error_code': code, 'description': TOKEN,
                           'parameters': {'retry_after': 60}}).encode()
        raise urllib.error.HTTPError(request.full_url, code, TOKEN, {}, BytesIO(body))
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', fail)
    with pytest.raises(telegram.TelegramError) as info:
        telegram.call(TOKEN, 'sendMessage', {'text': 'private'})
    assert TOKEN not in str(info.value)
    assert info.value.retryable is retryable and info.value.retry_after == 60


def test_timeout_does_not_expose_token(monkeypatch):
    def fail(*args, **kwargs):
        raise TimeoutError(TOKEN)
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', fail)
    with pytest.raises(telegram.TelegramError) as info:
        telegram.call(TOKEN, 'getMe')
    assert str(info.value) == 'telegram_network' and info.value.retryable
