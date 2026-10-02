import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import session
from .models import AuthSession, User

router = APIRouter(prefix='/api/auth', tags=['Авторизация'])
DB = Annotated[Session, Depends(session)]
COOKIE = 'lp_session'
TTL = 12 * 60 * 60
REMEMBER_TTL = 30 * 24 * 60 * 60
key_header = APIKeyHeader(name='X-Admin-Key', auto_error=False)
bearer = HTTPBearer(auto_error=False, description='Получите access_token через POST /api/auth/token. Только аккаунт admin управляет сайтом.')


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password, salt=None):
    # scrypt N=2^15,r=8,p=3; 32 MiB per verification, independent random salt.
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768,
                            r=8, p=3, maxmem=64*1024*1024, dklen=32).hex()
    return 'scrypt$' + salt + '$' + digest


def verify_password(password, encoded):
    try:
        method, salt, digest = encoded.split('$')
        if method != 'scrypt':
            return False
        return hmac.compare_digest(password_hash(password, salt), encoded)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = password_hash('dummy-password-not-a-real-account', '00'*16)


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=12, max_length=128)


class BrowserCredentials(Credentials):
    remember_me: bool = Field(default=False, strict=True,
                              description='Сохранить вход на этом устройстве на 30 дней. Без выбора — 12 часов.')


def public_user(user):
    return {'id': user.id, 'email': user.email, 'role': user.role}


def csrf_for(token):
    key = os.environ['ADMIN_API_KEY'].encode()
    return hmac.new(key, ('csrf:' + token).encode(), hashlib.sha256).hexdigest()


def resolve(request, db, authorization=None, required=True):
    token = authorization.credentials if authorization else request.cookies.get(COOKIE, '')
    item = db.get(AuthSession, hash_token(token)) if token else None
    user = db.get(User, item.user_id) if item and aware(item.expires_at) > now() else None
    if not user or not user.active:
        if required:
            raise HTTPException(401, 'Войдите в аккаунт.', headers={'WWW-Authenticate': 'Bearer'})
        return None, None
    if not authorization and request.method not in ('GET', 'HEAD', 'OPTIONS'):
        value = request.headers.get('X-CSRF-Token', '')
        if not hmac.compare_digest(value, csrf_for(token)):
            raise HTTPException(403, 'Защита сессии: обновите страницу и повторите действие.')
    return user, token


def require_user(request: Request, db: DB,
                 authorization: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    return resolve(request, db, authorization)[0]


def admin(request: Request, db: DB,
          key: Annotated[str | None, Depends(key_header)],
          authorization: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if key:
        if hmac.compare_digest(key.encode(), os.environ['ADMIN_API_KEY'].encode()):
            return
        raise HTTPException(401, 'Неверный ключ администратора.')
    user, _ = resolve(request, db, authorization)
    if user.role != 'admin':
        raise HTTPException(403, 'Доступ разрешён только администратору.')


def issue(db, user, response=None, *, ttl=TTL):
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= now()))
    db.add(AuthSession(token_hash=hash_token(token), user_id=user.id, expires_at=now()+timedelta(seconds=ttl)))
    # Bound the number of persistent sessions per account.
    old = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)
                     .order_by(AuthSession.created_at.desc()).offset(9)).all()
    for item in old:
        db.delete(item)
    db.commit()
    if response is not None:
        secure = os.getenv('APP_ENV', 'production') == 'production'
        response.set_cookie(COOKIE, token, max_age=ttl, secure=secure, httponly=True, samesite='lax', path='/')
    return token


def checked_user(data, db):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        raise HTTPException(401, 'Неверный email или пароль.')
    return user


@router.post('/register', status_code=201)
def register(data: BrowserCredentials, response: Response, db: DB):
    user = User(id=str(uuid4()), email=str(data.email).lower(), password_hash=password_hash(data.password), role='user')
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Регистрация недоступна для этого email. Попробуйте войти.')
    token = issue(db, user, response, ttl=REMEMBER_TTL if data.remember_me else TTL)
    return {'user': public_user(user), 'csrf_token': csrf_for(token)}


@router.post('/login')
def login(data: BrowserCredentials, response: Response, db: DB):
    user = checked_user(data, db)
    token = issue(db, user, response, ttl=REMEMBER_TTL if data.remember_me else TTL)
    return {'user': public_user(user), 'csrf_token': csrf_for(token)}


@router.post('/token')
def token(data: Credentials, db: DB):
    user = checked_user(data, db)
    return {'access_token': issue(db, user), 'token_type': 'bearer', 'expires_in': TTL}


@router.get('/me')
def me(request: Request, db: DB,
       authorization: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    user, token = resolve(request, db, authorization)
    return {'user': public_user(user), 'csrf_token': csrf_for(token)}


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, db: DB,
           authorization: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    _, token = resolve(request, db, authorization)
    db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    db.commit()
    response.delete_cookie(COOKIE, path='/')
