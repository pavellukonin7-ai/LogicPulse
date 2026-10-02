from datetime import datetime, timedelta, timezone
import hmac
import secrets
from typing import Annotated, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import admin, aware, hash_token, now
from .database import session
from .models import BehaviorMetric

router = APIRouter(tags=['Поведенческие метрики'])
DB = Annotated[Session, Depends(session)]
MSK = ZoneInfo('Europe/Moscow')
TARGETS = ('navigation', 'service', 'brief', 'submit', 'auth', 'form', 'other')


class Start(BaseModel):
    model_config = ConfigDict(extra='forbid')
    consent: Literal[True]
    page: Literal['/'] = '/'
    device: Literal['mobile', 'tablet', 'desktop']


class Point(BaseModel):
    model_config = ConfigDict(extra='forbid')
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    kind: Literal['move', 'click']


class Batch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sequence: int = Field(ge=1, le=10000)
    active_ms: int = Field(ge=0, le=3600000)
    points: list[Point] = Field(default_factory=list, max_length=60)
    clicks: dict[str, int] = Field(default_factory=dict, max_length=7)


@router.post('/api/metrics/sessions', status_code=201)
def start(data: Start, db: DB):
    token = secrets.token_urlsafe(32)
    row = BehaviorMetric(id=str(uuid4()), token_hash=hash_token(token), page=data.page, device=data.device)
    db.add(row)
    db.commit()
    return {'id': row.id, 'token': token}


def authorized(db, sid, token):
    row = db.scalar(select(BehaviorMetric).where(BehaviorMetric.id == sid).with_for_update())
    if not row or not token or not hmac.compare_digest(row.token_hash, hash_token(token)):
        raise HTTPException(404, 'Сессия метрик не найдена.')
    return row


@router.post('/api/metrics/sessions/{sid}')
def collect(sid: str, data: Batch, db: DB, x_metrics_token: Annotated[str | None, Header()] = None):
    row = authorized(db, sid, x_metrics_token)
    if data.sequence <= row.sequence:
        return {'accepted': True, 'sequence': row.sequence}
    elapsed = (now() - aware(row.started_at)).total_seconds()
    if elapsed > 7200:
        raise HTTPException(410, 'Сессия завершена.')
    if data.active_ms < row.active_ms or data.active_ms > max(0, elapsed)*1000 + 2000:
        raise HTTPException(422, 'Некорректная длительность.')
    if any(k not in TARGETS or type(v) is not int or not 0 <= v <= 50 for k, v in data.clicks.items()):
        raise HTTPException(422, 'Некорректные события.')
    row.active_ms, row.sequence, row.updated_at = data.active_ms, data.sequence, now()
    row.points = (row.points + [p.model_dump() for p in data.points])[-1000:]
    counts = dict(row.clicks)
    for k, v in data.clicks.items():
        counts[k] = min(10000, counts.get(k, 0) + v)
    row.clicks = counts
    db.commit()
    return {'accepted': True, 'sequence': row.sequence}


@router.delete('/api/metrics/sessions/{sid}', status_code=204)
def forget(sid: str, db: DB, x_metrics_token: Annotated[str | None, Header()] = None):
    row = authorized(db, sid, x_metrics_token)
    db.delete(row)
    db.commit()


def period_start(period, current=None):
    current = (current or now()).astimezone(MSK)
    day = current.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'week':
        day -= timedelta(days=day.weekday())
    elif period == 'month':
        day = day.replace(day=1)
    return day.astimezone(timezone.utc)


@router.get('/api/admin/metrics', dependencies=[Depends(admin)])
def summary(db: DB, period: Literal['day', 'week', 'month'] = 'day',
            device: Literal['mobile', 'tablet', 'desktop'] = 'desktop', kind: Literal['move', 'click'] = 'move'):
    current = now()
    base = select(BehaviorMetric).where(BehaviorMetric.started_at >= period_start('month', current) - timedelta(days=7))
    rows = db.scalars(base).all()
    averages = {}
    for p in ('day', 'week', 'month'):
        chosen = [r for r in rows if aware(r.started_at) >= period_start(p, current)]
        total = sum(r.active_ms for r in chosen)
        averages[p] = {'visits': len(chosen), 'active_seconds': round(total/1000, 1),
                       'average_seconds': round(total/1000/len(chosen), 1) if chosen else 0}
    selected = [r for r in rows if aware(r.started_at) >= period_start(period, current)
                and r.device == device and r.layout == 'home-1.2']
    cells, clicks = {}, {}
    for row in selected:
        for p in row.points:
            if p['kind'] == kind:
                cell = (min(39, int(p['x']*40)), min(79, int(p['y']*80)))
                cells[cell] = cells.get(cell, 0) + 1
        for k, v in row.clicks.items():
            clicks[k] = clicks.get(k, 0) + v
    return {'timezone': 'Europe/Moscow', 'averages': averages, 'period': period, 'device': device,
            'kind': kind, 'visits': len(selected), 'layout': 'home-1.2', 'clicks': clicks,
            'heatmap': [{'x': (x+.5)/40, 'y': (y+.5)/80, 'count': n} for (x,y),n in cells.items()],
            'note': 'Активное время видимой страницы на посещение. День/неделя/месяц — текущие календарные периоды МСК. Карта нормирована по ширине и полной высоте страницы; только согласившиеся посетители.'}
