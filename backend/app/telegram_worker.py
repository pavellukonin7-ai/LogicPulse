"""Durable outbox; PostgreSQL row lock prevents concurrent normal delivery.

Delivery is at-least-once: a lost HTTP response or crash after send may duplicate
the Telegram message. The stable request number makes such copies identifiable.
"""
import logging
import os
import signal
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select, text
from .database import SessionLocal
from .models import ProjectRequest, TelegramDelivery
from .telegram import TelegramError, send_notification, validate_token

logger = logging.getLogger('logicpulse.telegram')
HEARTBEAT = Path('/tmp/telegram-worker.heartbeat')


def deliver_one(factory, token, chat_id, sender=send_notification, now=None):
    now = now or datetime.now(timezone.utc)
    with factory() as db, db.begin():
        delivery = db.scalar(select(TelegramDelivery)
            .where(TelegramDelivery.status == 'pending', TelegramDelivery.next_attempt_at <= now)
            .order_by(TelegramDelivery.next_attempt_at)
            .with_for_update(skip_locked=True).limit(1))
        if delivery is None:
            return False
        row = db.get(ProjectRequest, delivery.request_id)
        delivery.attempts += 1
        try:
            message_id = sender(token, chat_id, row)
        except TelegramError as exc:
            delivery.last_error = str(exc)
            delivery.status = 'pending' if exc.retryable else 'failed'
            delay = max(exc.retry_after, min(3600, 30 * 2 ** min(delivery.attempts - 1, 7)))
            delivery.next_attempt_at = now + timedelta(seconds=delay)
            logger.warning('request=%s status=%s reason=%s', row.id, delivery.status, exc)
        else:
            delivery.status = 'sent'
            delivery.telegram_message_id = str(message_id)
            delivery.sent_at = datetime.now(timezone.utc)
            delivery.last_error = None
            logger.info('request=%s status=sent', row.id)
    return True


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    enabled = os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'
    token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN', ''), os.getenv('TELEGRAM_CHAT_ID', '')
    if enabled and (not validate_token(token) or not chat_id.isdigit() or int(chat_id) <= 0):
        logger.error('Telegram configuration invalid; run scripts/setup-telegram.py')
        raise SystemExit(1)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    logger.info('Telegram worker started; enabled=%s', enabled)
    while not stop.is_set():
        try:
            if enabled:
                deliver_one(SessionLocal, token, chat_id)
            else:
                with SessionLocal() as db:
                    db.execute(text('SELECT 1'))
            HEARTBEAT.touch()
        except Exception as exc:
            # URLs/SQL parameters can contain credentials/PII. Log only the type.
            logger.error('Worker cycle failed: %s', type(exc).__name__)
        stop.wait(2 if enabled else 15)


if __name__ == '__main__':
    main()
