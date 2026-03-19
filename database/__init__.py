# database/__init__.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from decouple import config
from sqlalchemy.pool import QueuePool

# Синхронный PostgreSQL
DATABASE_URL = config('DATABASE_URL')

# Синхронный движок
engine = create_engine(
    DATABASE_URL,
    pool_size=50,  # Увеличьте значительно
    max_overflow=100,  # Увеличьте значительно
    pool_timeout=5,  # Уменьшите timeout
    pool_recycle=900,  # Пересоздавать каждые 15 минут
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        db.expire_all()
        yield db
    finally:
        db.close()