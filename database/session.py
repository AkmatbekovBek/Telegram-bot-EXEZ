# database/session.py
from contextlib import contextmanager
from . import SessionLocal

@contextmanager
def db_session():
    """Безопасный контекстный менеджер для работы с БД"""
    db = SessionLocal()
    try:
        db.expire_all()
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()