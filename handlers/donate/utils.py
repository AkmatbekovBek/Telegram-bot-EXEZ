# handlers/donate/utils.py

import logging
from contextlib import contextmanager
from database import get_db

logger = logging.getLogger(__name__)

@contextmanager
def db_session():
    """Контекстный менеджер для безопасной работы с БД"""
    session = None
    try:
        session = next(get_db())
        yield session
    except Exception as e:
        logger.error(f"Database connection error in donate utils: {e}")
        if session:
            session.rollback()
        raise
    finally:
        if session:
            session.close()

def format_time_left(hours: int, minutes: int) -> str:
    """Форматирует оставшееся время"""
    if hours > 0 and minutes > 0:
        return f"{hours}ч {minutes}м"
    elif hours > 0:
        return f"{hours}ч"
    elif minutes > 0:
        return f"{minutes}м"
    else:
        return "менее минуты"