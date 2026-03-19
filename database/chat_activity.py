from sqlalchemy import Column, Integer, BigInteger, DateTime, String, func, and_, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import exists
from typing import Optional, List
import logging

Base = declarative_base()
logger = logging.getLogger(__name__)


class ChatActivity(Base):
    """Модель для хранения активности пользователей в чатах"""
    __tablename__ = 'chat_activity'

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    username = Column(String(100))
    first_name = Column(String(100))
    message_count = Column(Integer, default=1)
    last_activity = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())

    # Уникальный индекс на пару chat_id + user_id
    __table_args__ = (
        {'sqlite_autoincrement': True}
    )


class ChatActivityRepository:
    """Репозиторий для работы с активностью чатов"""

    @staticmethod
    def get_or_create(db, chat_id: int, user_id: int, username: str = None, first_name: str = None):
        """Получить или создать запись активности"""
        # Ищем существующую запись
        activity = db.query(ChatActivity).filter(
            and_(
                ChatActivity.chat_id == chat_id,
                ChatActivity.user_id == user_id
            )
        ).first()

        if not activity:
            # Создаем новую запись
            activity = ChatActivity(
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                first_name=first_name,
                message_count=1,
                last_activity=func.now()
            )
            db.add(activity)
        else:
            # Обновляем существующую
            activity.message_count += 1
            activity.last_activity = func.now()
            if username and not activity.username:
                activity.username = username
            if first_name and not activity.first_name:
                activity.first_name = first_name

        try:
            db.commit()
        except:
            db.rollback()
            raise

        return activity

    @staticmethod
    def get_chat_top_active(db, chat_id: int, limit: int = 10) -> List[ChatActivity]:
        """Получить топ активных пользователей в чате"""
        return db.query(ChatActivity).filter(
            ChatActivity.chat_id == chat_id
        ).order_by(
            ChatActivity.message_count.desc()
        ).limit(limit).all()

    @staticmethod
    def get_total_messages(db, chat_id: int) -> int:
        """Получить общее количество сообщений в чате"""
        result = db.query(func.sum(ChatActivity.message_count)).filter(
            ChatActivity.chat_id == chat_id
        ).scalar()

        return result or 0

    @staticmethod
    def reset_chat_activity(db, chat_id: int):
        """Сбросить статистику для чата"""
        db.query(ChatActivity).filter(
            ChatActivity.chat_id == chat_id
        ).delete()

        try:
            db.commit()
        except:
            db.rollback()
            raise

    @staticmethod
    def get_user_position(db, chat_id: int, user_id: int) -> Optional[int]:
        """Получить позицию пользователя в рейтинге по количеству сообщений"""
        try:
            # Получаем всех пользователей чата отсортированных по message_count
            all_users = db.query(ChatActivity).filter(
                ChatActivity.chat_id == chat_id,
                ChatActivity.message_count > 0
            ).order_by(ChatActivity.message_count.desc()).all()

            # Ищем пользователя и возвращаем его позицию
            for i, user in enumerate(all_users, 1):
                if user.user_id == user_id:
                    return i
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении позиции пользователя: {e}")
            return None

    @staticmethod
    def get_user_activity(db, chat_id: int, user_id: int) -> Optional[ChatActivity]:
        """Получить активность конкретного пользователя"""
        try:
            return db.query(ChatActivity).filter(
                ChatActivity.chat_id == chat_id,
                ChatActivity.user_id == user_id
            ).first()
        except Exception as e:
            logger.error(f"Ошибка при получении активности пользователя: {e}")
            return None

    @staticmethod
    def get_user_position_optimized(db, chat_id: int, user_id: int) -> Optional[int]:
        """
        Оптимизированный метод получения позиции пользователя
        (использует SQL запрос вместо загрузки всех данных)
        """
        try:
            # Используем оконную функцию ROW_NUMBER для получения позиции
            # В SQLite оконные функции доступны начиная с версии 3.25.0
            sql = text("""
                       WITH ranked_users AS (SELECT user_id,
                                                    message_count,
                                                    ROW_NUMBER() OVER (ORDER BY message_count DESC) as position
                       FROM chat_activity
                       WHERE chat_id = :chat_id
                         AND message_count
                           > 0
                           )
                       SELECT position
                       FROM ranked_users
                       WHERE user_id = :user_id
                       """)

            result = db.execute(sql, {"chat_id": chat_id, "user_id": user_id}).fetchone()
            return result[0] if result else None

        except Exception as e:
            logger.error(f"Ошибка при получении позиции пользователя (оптимизировано): {e}")
            # Если оконные функции не поддерживаются, используем обычный метод
            return ChatActivityRepository.get_user_position(db, chat_id, user_id)

    @staticmethod
    def get_user_message_count(db, chat_id: int, user_id: int) -> int:
        """Получить количество сообщений конкретного пользователя"""
        try:
            activity = ChatActivityRepository.get_user_activity(db, chat_id, user_id)
            return activity.message_count if activity else 0
        except Exception as e:
            logger.error(f"Ошибка при получении количества сообщений пользователя: {e}")
            return 0