import os
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Base(DeclarativeBase):
    pass

def database_url():
    # DATABASE_URL is intended for isolated tests. Production uses separate fields:
    # URL.create correctly escapes special characters in database passwords.
    if os.getenv('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    return URL.create('postgresql+psycopg', username=os.environ['POSTGRES_USER'],
                      password=os.environ['POSTGRES_PASSWORD'], host=os.getenv('DB_HOST', 'db'),
                      port=5432, database=os.environ['POSTGRES_DB'])

url = database_url()
engine = create_engine(url, pool_pre_ping=True,
                       connect_args={'check_same_thread': False} if str(url).startswith('sqlite') else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def session():
    with SessionLocal() as db:
        yield db
