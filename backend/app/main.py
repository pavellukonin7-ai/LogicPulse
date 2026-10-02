import hashlib
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import APIKeyHeader
from sqlalchemy import select, text, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from .database import Base, engine, session
from .models import ProjectRequest, Service, TelegramDelivery, ArchivedService, LeadAssessment, ServiceDetails
from .auth import admin, router as auth_router
from .priorities import score_lead
from .schemas import Receipt, RequestInput, ServiceAdmin, ServiceInput, ServicePublic

logger = logging.getLogger('logicpulse')
admin_key = os.environ.get('ADMIN_API_KEY', '')
if len(admin_key) < 32:
    raise RuntimeError('ADMIN_API_KEY must contain at least 32 characters')

@asynccontextmanager
async def lifespan(app):
    # Initial, additive schema only. Existing PostgreSQL volumes are never recreated.
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title='LogicPulse API', version='1.2.0', lifespan=lifespan,
              description='Вход: POST /api/auth/token, затем Authorize → HTTPBearer. Администрирование требует роли admin. X-Admin-Key сохранён для серверных инструментов.',
              docs_url=None, redoc_url=None)
DB = Annotated[Session, Depends(session)]
app.include_router(auth_router)

@app.get('/docs', include_in_schema=False)
def swagger():
    return get_swagger_ui_html(openapi_url='/openapi.json', title='LogicPulse — Swagger',
        swagger_js_url='/swagger/swagger-ui-bundle.js', swagger_css_url='/swagger/swagger-ui.css',
        swagger_favicon_url='/favicon.svg', swagger_ui_parameters={'persistAuthorization': False})

@app.middleware('http')
async def headers(request: Request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        expected = os.getenv('APP_ORIGIN', 'https://logicpulse.ru').rstrip('/')
        if (origin and origin != expected) or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse(status_code=403, content={'detail': 'Запрос с другого сайта отклонён.'})
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.exception_handler(RequestValidationError)
async def invalid_input(request, exc):
    # FastAPI's default input echo could otherwise include a password.
    return JSONResponse(status_code=422, content={'detail': [
        {'loc': e['loc'], 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]})

@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    # Do not log SQL parameters: request bodies contain personal information.
    logger.error('Database operation failed: %s', type(exc).__name__)
    return JSONResponse(status_code=503, content={'detail': 'Сервис временно недоступен. Повторите попытку позже.'})

@app.get('/api/health', tags=['Диагностика'])
def health(db: DB):
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'database': 'connected'}

DETAIL_FIELDS = ('scope_items', 'delivery_time', 'public_note', 'button_text')


def service_view(row, db, *, public=False):
    details = db.get(ServiceDetails, row.id)
    extra = {key: getattr(details, key) for key in DETAIL_FIELDS} if details else {}
    if public:
        return ServicePublic(id=row.id, slug=row.slug, name=row.name, description=row.description,
            price_min=row.price_min if row.prices_approved else None,
            price_max=row.price_max if row.prices_approved else None, **extra)
    return ServiceAdmin.model_validate(row).model_copy(update=extra)


@app.get('/api/services', response_model=list[ServicePublic], tags=['Услуги'])
def services(db: DB):
    rows = db.scalars(select(Service).where(Service.active.is_(True)).order_by(Service.id)).all()
    return [service_view(s, db, public=True) for s in rows]

@app.get('/api/admin/services', response_model=list[ServiceAdmin], dependencies=[Depends(admin)], tags=['Администрирование'])
def admin_services(db: DB):
    rows = db.scalars(select(Service).where(~Service.id.in_(select(ArchivedService.service_id))).order_by(Service.id)).all()
    return [service_view(s, db) for s in rows]

@app.post('/api/services', response_model=ServiceAdmin, status_code=201, dependencies=[Depends(admin)], tags=['Услуги'])
def create_service(data: ServiceInput, db: DB):
    service = Service(**data.model_dump(exclude=set(DETAIL_FIELDS)))
    db.add(service)
    try:
        db.flush()
        db.add(ServiceDetails(service_id=service.id, **data.model_dump(include=set(DETAIL_FIELDS))))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Услуга с таким slug уже существует.')
    return service_view(service, db)

@app.put('/api/services/{service_id}', response_model=ServiceAdmin, dependencies=[Depends(admin)], tags=['Услуги'])
def update_service(service_id: int, data: ServiceInput, db: DB):
    service = db.get(Service, service_id)
    if not service or db.get(ArchivedService, service_id):
        raise HTTPException(404, 'Услуга не найдена.')
    for key, value in data.model_dump(exclude=set(DETAIL_FIELDS)).items():
        setattr(service, key, value)
    changed_details = data.model_dump(include=set(DETAIL_FIELDS), exclude_unset=True)
    if changed_details:
        details = db.get(ServiceDetails, service_id)
        if details is None:
            details = ServiceDetails(service_id=service_id)
            db.add(details)
        for key, value in changed_details.items():
            setattr(details, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Услуга с таким slug уже существует.')
    return service_view(service, db)

@app.get('/api/services/{service_id}', response_model=ServicePublic, tags=['Услуги'])
def service_detail(service_id: int, db: DB):
    row = db.get(Service, service_id)
    if not row or not row.active:
        raise HTTPException(404, 'Услуга не найдена.')
    return service_view(row, db, public=True)

@app.delete('/api/services/{service_id}', status_code=204, dependencies=[Depends(admin)], tags=['Услуги'])
def delete_service(service_id: int, db: DB):
    row = db.scalar(select(Service).where(Service.id == service_id).with_for_update())
    if not row or db.get(ArchivedService, service_id):
        raise HTTPException(404, 'Услуга не найдена.')
    row.active = False
    db.add(ArchivedService(service_id=service_id))
    db.commit()
    return Response(status_code=204)

@app.post('/api/requests', response_model=Receipt, status_code=201, tags=['Заявки'])
def create_request(data: RequestInput, db: DB):
    payload = data.model_dump(mode='json', exclude={'request_id', 'urgency', 'budget'})
    if data.urgency is not None:
        payload['urgency'] = data.urgency
    if data.budget is not None:
        payload['budget'] = data.budget
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    request_id = str(data.request_id)
    existing = db.get(ProjectRequest, request_id)
    if existing:
        if not hmac.compare_digest(existing.payload_hash, digest):
            raise HTTPException(409, 'Идентификатор уже использован для другой заявки. Обновите страницу.')
        return Receipt(id=existing.id)
    service = db.get(Service, data.service_id)
    if not service or not service.active:
        raise HTTPException(422, 'Выберите доступную услугу.')
    row = ProjectRequest(id=request_id, service_id=service.id, service_name=service.name,
        name=data.name, email=str(data.email), company=data.company, message=data.message, payload_hash=digest)
    db.add(row)
    try:
        db.flush()
        db.add(LeadAssessment(request_id=row.id, **score_lead(data.urgency, data.budget, data.company, data.message)))
        if os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true':
            db.add(TelegramDelivery(request_id=row.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(ProjectRequest, request_id)
        if existing and hmac.compare_digest(existing.payload_hash, digest):
            return Receipt(id=existing.id)
        raise HTTPException(409, 'Не удалось сохранить заявку. Обновите страницу.')
    return Receipt(id=row.id)

@app.get('/api/admin/requests', dependencies=[Depends(admin)], tags=['Администрирование'])
def list_requests(db: DB, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
                  include_test: bool = True):
    query = select(ProjectRequest, LeadAssessment).outerjoin(LeadAssessment, LeadAssessment.request_id == ProjectRequest.id)
    if not include_test:
        query = query.where((LeadAssessment.is_test.is_(False)) | (LeadAssessment.request_id.is_(None)))
    rows = db.execute(query.order_by(func.coalesce(LeadAssessment.score, -1).desc(),
        ProjectRequest.created_at.desc(), ProjectRequest.id).offset(offset).limit(limit)).all()
    return [request_view(r, a) for r, a in rows]

def request_view(r, a):
    return {'id': r.id, 'service_id': r.service_id, 'service_name': r.service_name,
             'name': r.name, 'email': r.email, 'company': r.company, 'message': r.message,
             'created_at': r.created_at, 'consent_version': r.consent_version,
             'assessment': None if a is None else {
                 'score': a.score, 'temperature': a.temperature, 'reasons': a.reasons,
                 'urgency': a.urgency, 'budget': a.budget, 'is_test': a.is_test, 'rule_version': a.rule_version}}

@app.get('/api/admin/requests/{request_id}', dependencies=[Depends(admin)], tags=['Администрирование'])
def request_detail(request_id: str, db: DB):
    row = db.get(ProjectRequest, request_id)
    if row is None:
        raise HTTPException(404, 'Заявка не найдена.')
    return request_view(row, db.get(LeadAssessment, request_id))

@app.get('/api/admin/telegram', dependencies=[Depends(admin)], tags=['Администрирование'])
def telegram_status(db: DB):
    from sqlalchemy import func
    counts = dict(db.execute(select(TelegramDelivery.status, func.count()).group_by(TelegramDelivery.status)).all())
    rows = db.scalars(select(TelegramDelivery).order_by(TelegramDelivery.next_attempt_at.desc()).limit(20)).all()
    return {'enabled': os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true',
            'counts': {s: counts.get(s, 0) for s in ('pending', 'sent', 'failed')},
            'recent': [{'request_id': r.request_id, 'status': r.status, 'attempts': r.attempts,
                        'last_error': r.last_error, 'sent_at': r.sent_at,
                        'next_attempt_at': r.next_attempt_at if r.status == 'pending' else None} for r in rows]}

@app.post('/api/admin/telegram/{request_id}/retry', dependencies=[Depends(admin)], tags=['Администрирование'])
def retry_telegram(request_id: str, db: DB):
    from datetime import datetime, timezone
    row = db.scalar(select(TelegramDelivery).where(TelegramDelivery.request_id == request_id).with_for_update())
    if row is None:
        raise HTTPException(404, 'Уведомление не найдено.')
    if row.status != 'failed':
        raise HTTPException(409, 'Повтор доступен только для уведомлений со статусом failed.')
    row.status = 'pending'
    row.last_error = None
    row.next_attempt_at = datetime.now(timezone.utc)
    db.commit()
    return {'request_id': row.request_id, 'status': row.status}

from .metrics import router as metrics_router
app.include_router(metrics_router)
