from datetime import datetime, timedelta, timezone
from collections import Counter
from sqlalchemy import select
from test_api import client, new_service, new_request, SERVICE, KEY
from app.models import User, AuthSession, BehaviorMetric, TelegramDelivery
from app.priorities import score_lead
from app.metrics import period_start
from app.manage import seed, cleanup_tests

CREDS={'email':'person@example.com','password':'A-long-test-password-12'}

def login_admin(client):
    client.post('/api/auth/register',json=CREDS)
    with client.test_factory() as db:
        user=db.scalar(select(User));user.role='admin';db.commit()
    return client.post('/api/auth/token',json=CREDS).json()['access_token']

def test_registration_cannot_self_assign_admin_and_hashes_secrets(client):
    assert client.post('/api/auth/register',json={**CREDS,'role':'admin'}).status_code==422
    r=client.post('/api/auth/register',json=CREDS)
    assert r.status_code==201 and r.json()['user']['role']=='user'
    assert 'HttpOnly' in r.headers['set-cookie'] and 'Secure' in r.headers['set-cookie']
    assert CREDS['password'] not in r.text
    with client.test_factory() as db:
        u=db.scalar(select(User));assert u.password_hash.startswith('scrypt$')
        item=db.scalar(select(AuthSession));assert len(item.token_hash)==64
    assert client.post('/api/auth/register',json=CREDS).status_code==409
    r=client.post('/api/auth/register',json={**CREDS,'password':'short'})
    assert r.status_code==422 and '"input"' not in r.text

def test_bearer_role_and_revocation(client):
    client.post('/api/auth/register',json=CREDS)
    token=client.post('/api/auth/token',json=CREDS).json()['access_token']
    headers={'Authorization':'Bearer '+token}
    assert client.get('/api/auth/me',headers=headers).status_code==200
    assert client.get('/api/admin/services',headers=headers).status_code==403
    assert client.post('/api/auth/logout',headers=headers).status_code==204
    assert client.get('/api/auth/me',headers=headers).status_code==401
    assert client.post('/api/auth/login',json={**CREDS,'password':'wrong-password-123'}).status_code==401

def test_cookie_csrf_and_cross_origin_enforced(client,monkeypatch):
    monkeypatch.setenv('APP_ENV','test')
    login_admin(client)
    me=client.get('/api/auth/me').json()
    assert client.post('/api/services',json=SERVICE).status_code==403
    assert client.post('/api/services',json=SERVICE,headers={'X-CSRF-Token':me['csrf_token']}).status_code==201
    assert client.post('/api/services',json={**SERVICE,'slug':'other'},headers={'X-CSRF-Token':me['csrf_token'],'Origin':'https://evil.example'}).status_code==403

def test_sessions_expire(client):
    token=login_admin(client)
    with client.test_factory() as db:
        for item in db.scalars(select(AuthSession)).all(): item.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        db.commit()
    assert client.get('/api/auth/me',headers={'Authorization':'Bearer '+token}).status_code==401

def test_full_service_crud_preserves_requests(client):
    token=login_admin(client);headers={'Authorization':'Bearer '+token}
    s=client.post('/api/services',headers=headers,json=SERVICE).json()
    assert client.get('/api/services/'+str(s['id'])).status_code==200
    assert client.put('/api/services/'+str(s['id']),headers=headers,json={**SERVICE,'name':'Обновлённая услуга'}).status_code==200
    r=client.post('/api/requests',json=new_request(s['id'])).json()
    assert client.delete('/api/services/'+str(s['id']),headers=headers).status_code==204
    assert client.get('/api/services').json()==[]
    assert client.get('/api/admin/services',headers=headers).json()==[]
    assert client.get('/api/services/'+str(s['id'])).status_code==404
    assert client.get('/api/admin/requests/'+r['id'],headers=headers).status_code==200
    assert client.put('/api/services/'+str(s['id']),headers=headers,json=SERVICE).status_code==404

def test_seed_distribution_ranking_idempotency_and_cleanup(client,monkeypatch):
    monkeypatch.setenv('TELEGRAM_ENABLED','true')
    s=new_service(client)
    real=client.post('/api/requests',json=new_request(s['id'])).json()['id']
    with client.test_factory() as db: seed(db);seed(db)
    rows=client.get('/api/admin/requests',headers=KEY).json()
    tests=[r for r in rows if r['assessment']['is_test']]
    assert len(tests)==10
    assert Counter(r['assessment']['temperature'] for r in tests)=={'hot':4,'warm':3,'cold':3}
    assert [r['assessment']['score'] for r in rows]==sorted([r['assessment']['score'] for r in rows],reverse=True)
    assert len(client.get('/api/admin/requests?include_test=false',headers=KEY).json())==1
    with client.test_factory() as db:
        assert len(db.scalars(select(TelegramDelivery)).all())==1
        cleanup_tests(db)
    assert client.get('/api/admin/requests',headers=KEY).json()[0]['id']==real

def test_scoring_boundaries():
    assert score_lead('urgent',100000,'','x')['score']==65
    assert score_lead('urgent',100000,'','x')['temperature']=='hot'
    assert score_lead('soon',None,'company','x')['temperature']=='warm'
    assert score_lead('research',None,'','x')['temperature']=='cold'

def test_metrics_consent_auth_bounds_idempotency_and_summary(client):
    assert client.post('/api/metrics/sessions',json={'consent':False,'device':'desktop'}).status_code==422
    s=client.post('/api/metrics/sessions',json={'consent':True,'device':'desktop'}).json()
    url='/api/metrics/sessions/'+s['id'];h={'X-Metrics-Token':s['token']}
    with client.test_factory() as db:
        row=db.get(BehaviorMetric,s['id']);row.started_at=datetime.now(timezone.utc)-timedelta(seconds=180);db.commit()
    batch={'sequence':1,'active_ms':150000,'points':[{'x':.5,'y':.25,'kind':'move'}], 'clicks':{'form':3}}
    assert client.post(url,json=batch).status_code==404
    assert client.post(url,json=batch,headers=h).status_code==200
    assert client.post(url,json=batch,headers=h).status_code==200
    assert client.post(url,json={**batch,'sequence':2,'active_ms':999999},headers=h).status_code==422
    assert client.get('/api/admin/metrics').status_code==401
    data=client.get('/api/admin/metrics',headers=KEY).json()
    assert data['averages']['day']['average_seconds']==150
    assert data['clicks']['form']==3 and data['heatmap'][0]['count']==1
    assert 'token_hash' not in str(data)
    assert client.delete(url,headers=h).status_code==204
    assert client.get('/api/admin/metrics',headers=KEY).json()['averages']['day']['visits']==0

def test_metric_calendar_moscow():
    current=datetime(2026,10,1,0,15,tzinfo=timezone.utc)
    assert period_start('month',current)==datetime(2026,9,30,21,tzinfo=timezone.utc)
    assert period_start('week',current)==datetime(2026,9,27,21,tzinfo=timezone.utc)
