from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class Service(Base):
    __tablename__ = 'lp_services'
    __table_args__ = (CheckConstraint('price_min >= 0 AND price_max >= price_min'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    price_min: Mapped[int] = mapped_column(Integer)
    price_max: Mapped[int] = mapped_column(Integer)
    prices_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    price_review_note: Mapped[str] = mapped_column(Text, default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class ServiceDetails(Base):
    """Additive presentation data; existing services do not need rewriting."""
    __tablename__ = 'lp_service_details'
    service_id: Mapped[int] = mapped_column(ForeignKey('lp_services.id'), primary_key=True)
    scope_items: Mapped[list] = mapped_column(JSON, default=list)
    delivery_time: Mapped[str] = mapped_column(String(80), default='')
    public_note: Mapped[str] = mapped_column(Text, default='')
    button_text: Mapped[str] = mapped_column(String(80), default='Обсудить проект')

class ProjectRequest(Base):
    __tablename__ = 'lp_requests'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey('lp_services.id'))
    service_name: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    company: Mapped[str] = mapped_column(String(160), default='')
    message: Mapped[str] = mapped_column(Text)
    consent_version: Mapped[str] = mapped_column(String(40), default='2026-09-30-admin')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    payload_hash: Mapped[str] = mapped_column(String(64))

class TelegramDelivery(Base):
    __tablename__ = 'lp_telegram_deliveries'
    __table_args__ = (CheckConstraint("status IN ('pending', 'sent', 'failed')"),)
    request_id: Mapped[str] = mapped_column(ForeignKey('lp_requests.id'), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default='pending', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    last_error: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_message_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


class User(Base):
    __tablename__ = 'lp_users'
    __table_args__ = (CheckConstraint("role IN ('user','admin')"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default='user')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuthSession(Base):
    __tablename__ = 'lp_auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('lp_users.id'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ArchivedService(Base):
    __tablename__ = 'lp_archived_services'
    service_id: Mapped[int] = mapped_column(ForeignKey('lp_services.id'), primary_key=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LeadAssessment(Base):
    __tablename__ = 'lp_lead_assessments'
    __table_args__ = (CheckConstraint('score >= 0 AND score <= 100'),
                     CheckConstraint("temperature IN ('hot','warm','cold')"))
    request_id: Mapped[str] = mapped_column(ForeignKey('lp_requests.id'), primary_key=True)
    score: Mapped[int] = mapped_column(Integer, index=True)
    temperature: Mapped[str] = mapped_column(String(12), index=True)
    urgency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasons: Mapped[list] = mapped_column(JSON)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(16), default='1.2.0')


class BehaviorMetric(Base):
    __tablename__ = 'behavior_metrics'
    __table_args__ = (CheckConstraint('active_ms >= 0'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    page: Mapped[str] = mapped_column(String(80), default='/')
    layout: Mapped[str] = mapped_column(String(20), default='home-1.2')
    device: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    active_ms: Mapped[int] = mapped_column(Integer, default=0)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[list] = mapped_column(JSON, default=list)
    clicks: Mapped[dict] = mapped_column(JSON, default=dict)
    consent_version: Mapped[str] = mapped_column(String(32), default='analytics-2026-09-30')
