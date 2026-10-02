"""Explicit maintenance commands; never called implicitly on container startup."""
import argparse
import getpass
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import delete, select
from email_validator import validate_email
from .auth import now, password_hash
from .database import Base, engine, SessionLocal
from .models import User, AuthSession, BehaviorMetric, ProjectRequest, Service, LeadAssessment, TelegramDelivery
from .priorities import score_lead

TEST_PREFIX = '12000000-0000-4000-8000-'
MESSAGE = 'Тестовая заявка для проверки ранжирования LogicPulse. Требуется автоматизировать обработку обращений, интеграцию систем и отчётность. Реальным клиентом не является.'

def seed(db):
    service = db.scalar(select(Service).where(Service.active.is_(True)).order_by(Service.id))
    if not service:
        raise ValueError('Сначала добавьте хотя бы одну активную услугу через админ-панель.')
    for i in range(1, 11):
        sid = TEST_PREFIX + str(i).zfill(12)
        existing = db.get(ProjectRequest, sid)
        if existing and existing.consent_version != 'test-fixture-1.2':
            raise ValueError('Конфликт тестовых идентификаторов; данные не изменены.')
        if existing:
            continue
        urgency = 'urgent' if i <= 4 else 'soon' if i <= 7 else 'research'
        budget = 300000 if i <= 4 else None
        row = ProjectRequest(id=sid, service_id=service.id, service_name=service.name,
                             name=f'Тестовый клиент {i:02}', email=f'demo{i}@example.com',
                             company='Тест LogicPulse', message=MESSAGE,
                             consent_version='test-fixture-1.2', payload_hash='0'*64)
        db.add(row); db.flush()
        db.add(LeadAssessment(request_id=sid, is_test=True, **score_lead(urgency,budget,row.company,row.message)))
    db.commit()


def cleanup_tests(db):
    rows = db.scalars(select(ProjectRequest).join(LeadAssessment)
                      .where(LeadAssessment.is_test.is_(True), ProjectRequest.consent_version=='test-fixture-1.2')).all()
    for row in rows:
        if not row.id.startswith(TEST_PREFIX):
            continue
        db.execute(delete(TelegramDelivery).where(TelegramDelivery.request_id == row.id))
        db.delete(db.get(LeadAssessment, row.id)); db.flush(); db.delete(row)
    db.commit()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['admin', 'seed-tests', 'remove-tests', 'housekeeping'])
    args = p.parse_args()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if args.command == 'admin':
            email = validate_email(input('Email администратора: ').strip(), check_deliverability=False).normalized.lower()
            password = getpass.getpass('Новый пароль (от 12 символов, ввод скрыт): ')
            if len(password) < 12 or len(password) > 128:
                raise ValueError('Пароль должен содержать от 12 до 128 символов.')
            if password != getpass.getpass('Повторите пароль: '):
                raise ValueError('Пароли не совпали.')
            user = db.scalar(select(User).where(User.email==email))
            if user is None:
                user = User(id=str(uuid4()), email=email, role='admin', password_hash=password_hash(password)); db.add(user)
            else:
                user.role='admin'; user.active=True; user.password_hash=password_hash(password)
                db.execute(delete(AuthSession).where(AuthSession.user_id==user.id))
            db.commit()
            print('Администратор сохранён. Вход: https://logicpulse.ru/account.html')
        elif args.command == 'seed-tests':
            seed(db); print('Готово: 10 тестовых заявок (4 высоких, 3 средних, 3 низких). Telegram не вызывается.')
        elif args.command == 'remove-tests':
            cleanup_tests(db); print('Тестовые заявки удалены. Рабочие заявки сохранены.')
        else:
            db.execute(delete(AuthSession).where(AuthSession.expires_at <= now()))
            db.execute(delete(BehaviorMetric).where(BehaviorMetric.started_at < now()-timedelta(days=90)))
            db.commit(); print('Просроченные сессии и метрики старше 90 дней удалены.')

if __name__=='__main__':
    try: main()
    except (ValueError, KeyboardInterrupt) as exc: raise SystemExit(str(exc) or 'Отмена.')
