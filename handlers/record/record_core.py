import logging
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple
from aiogram import types
from sqlalchemy import func

from database import get_db, SessionLocal
from database.crud import UserRepository, DailyRecordRepository, ChatRepository
from database.models import DailyRecord, TelegramUser


class RecordConfig:
    """Конфигурация рекордов"""
    BOT_ADMIN_IDS = [1054684037]
    DEFAULT_TOP_LIMIT = 10
    MAX_TOP_LIMIT = 100
    MEDALS = ["🥇", "🥈", "🥉"]
    RECORD_RESET_HOURS = 24  # Рекорд сбрасывается каждые 24 часа


class RecordErrors:
    """Классы ошибок"""

    class RecordError(Exception):
        pass

    class InsufficientPermissionsError(RecordError):
        pass

    class DatabaseError(RecordError):
        pass

    class ValidationError(RecordError):
        pass


class RecordCore:
    """Основная логика работы с рекордами"""

    def __init__(self):
        self.config = RecordConfig()
        self.logger = logging.getLogger(__name__)
        self._setup_logging()
        self._record_service = None  # Добавляем ссылку на сервис

    def _setup_logging(self):
        """Настройка логирования"""
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    @contextmanager
    def db_session(self):
        """Контекстный менеджер для сессии БД"""
        db = SessionLocal()
        try:
            yield db
            db.commit()  # ДОБАВЬТЕ ЭТУ СТРОКУ!
        except Exception as e:
            db.rollback()
            self.logger.error(f"Database error: {e}")
            raise RecordErrors.DatabaseError(f"Database operation failed: {e}")
        finally:
            db.close()

    def _get_user_profile_link(self, user_id: int, display_name: str) -> str:
        """Создает кликабельную ссылку на профиль пользователя"""
        if not display_name or display_name == "Аноним":
            return "Аноним"

        # Экранирование HTML-символов для безопасности
        safe_name = display_name.replace('<', '&lt;').replace('>', '&gt;')
        return f'<a href="tg://user?id={user_id}">{safe_name}</a>'

    async def _check_admin_rights(self, message_or_callback) -> bool:
        """Проверяет, является ли пользователь администратором группы или бота"""
        try:
            if isinstance(message_or_callback, types.Message):
                user_id = message_or_callback.from_user.id
                chat_id = message_or_callback.chat.id
            else:  # types.CallbackQuery
                user_id = message_or_callback.from_user.id
                chat_id = message_or_callback.message.chat.id

            # Проверяем админов бота
            if user_id in self.config.BOT_ADMIN_IDS:
                return True

            # Проверяем админов из БД
            with self.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if user and user.is_admin:
                    return True

            # Проверяем администраторов группы
            if chat_id < 0:  # Это группа/супергруппа
                try:
                    chat_member = await message_or_callback.bot.get_chat_member(chat_id, user_id)
                    return chat_member.status in ['administrator', 'creator']
                except Exception:
                    return False

            return False

        except Exception as e:
            self.logger.error(f"Error in _check_admin_rights: {e}")
            return False

    async def _send_not_admin_message(self, message_or_callback):
        """Отправляет сообщение об отсутствии прав"""
        text = "❌ Эта команда доступна только администраторам группы или бота"
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(text)
        else:  # types.CallbackQuery
            await message_or_callback.answer(text, show_alert=True)

    async def ensure_user_registered(self, user_id: int, chat_id: int, username: str = None,
                                     first_name: str = None):
        """Автоматически регистрирует пользователя в чате"""
        with self.db_session() as db:
            ChatRepository.add_user_to_chat(db, user_id, chat_id, username, first_name)

    def _get_global_top_wins_today(self, limit: int) -> List[Tuple]:
        """Получает глобальный топ рекордов выигрышей за сегодня - уникальный по пользователю"""
        with self.db_session() as db:
            today = date.today()
            try:
                # Используем подзапрос для получения максимального выигрыша каждого пользователя
                subquery = (db.query(
                    DailyRecord.user_id,
                    func.max(DailyRecord.amount).label('max_amount')
                )
                            .filter(DailyRecord.record_date == today)
                            .group_by(DailyRecord.user_id)
                            .subquery())

                # Теперь получаем топ по уникальным пользователям
                top_records = (db.query(
                    subquery.c.user_id,
                    func.coalesce(TelegramUser.first_name, TelegramUser.username, 'Аноним').label('display_name'),
                    subquery.c.max_amount
                )
                               .join(TelegramUser, TelegramUser.telegram_id == subquery.c.user_id)
                               .order_by(subquery.c.max_amount.desc())
                               .limit(limit)
                               .all())

                # ДЕЛАЕМ ВСЕ ИМЕНА КЛИКАБЕЛЬНЫМИ
                return [(record.user_id,
                         self._get_user_profile_link(record.user_id, record.display_name),
                         record.max_amount) for record in top_records]
            except Exception as e:
                self.logger.error(f"Error in _get_global_top_wins_today: {e}")
                return []

    # handlers/record/record_core.py

    def _get_global_top_losses_today(self, limit: int) -> List[Tuple]:
        """Получает глобальный топ рекордов проигрышей за сегодня из DailyLossRecord"""
        with self.db_session() as db:
            try:
                from database.crud import DailyRecordRepository

                # Используем новую таблицу DailyLossRecord
                top_losses = DailyRecordRepository.get_top_losses_today(db, 0, limit)  # chat_id=0 для глобального топа

                # ДЕЛАЕМ ВСЕ ИМЕНА КЛИКАБЕЛЬНЫМИ
                return [(user_id,
                         self._get_user_profile_link(user_id, display_name),
                         amount) for user_id, display_name, amount in top_losses]
            except Exception as e:
                self.logger.error(f"Error in _get_global_top_losses_today: {e}")
                return []

    def _get_user_global_rank_today(self, user_id: int) -> Optional[int]:
        """Получает глобальную позицию пользователя в рекордах выигрышей"""
        with self.db_session() as db:
            today = date.today()
            try:
                user_record = (db.query(func.max(DailyRecord.amount))
                               .filter(
                    DailyRecord.user_id == user_id,
                    DailyRecord.record_date == today
                )
                               .scalar())

                if not user_record:
                    return None

                subquery = (db.query(
                    DailyRecord.user_id,
                    func.max(DailyRecord.amount).label('max_amount')
                )
                            .filter(DailyRecord.record_date == today)
                            .group_by(DailyRecord.user_id)
                            .subquery())

                rank = (db.query(func.count(subquery.c.user_id))
                        .filter(subquery.c.max_amount > user_record)
                        .scalar())

                return rank + 1 if rank is not None else 1

            except Exception as e:
                self.logger.error(f"Error in _get_user_global_rank_today: {e}")
                return None

    def _get_user_loss_rank_today(self, user_id: int) -> Optional[int]:
        """Получает глобальную позицию пользователя в рекордах проигрышей"""
        with self.db_session() as db:
            try:
                user_loss = (db.query(TelegramUser.defeat_coins)
                             .filter(TelegramUser.telegram_id == user_id)
                             .scalar())

                if not user_loss or user_loss <= 0:
                    return None

                rank = (db.query(func.count(TelegramUser.telegram_id))
                        .filter(TelegramUser.defeat_coins > user_loss)
                        .scalar())

                return rank + 1 if rank is not None else 1
            except Exception as e:
                self.logger.error(f"Error in _get_user_loss_rank_today: {e}")
                return None

    def _get_user_daily_record_global(self, user_id: int):
        """Получает глобальный рекорд пользователя за сегодня (максимальный, если несколько)"""
        with self.db_session() as db:
            today = date.today()
            try:
                user_record = (db.query(DailyRecord)
                               .filter(
                    DailyRecord.user_id == user_id,
                    DailyRecord.record_date == today
                )
                               .order_by(DailyRecord.amount.desc())
                               .first())
                return user_record
            except Exception as e:
                self.logger.error(f"Error in _get_user_daily_record_global: {e}")
                return None

    def _get_user_loss_record(self, user_id: int):
        """Получает рекорд проигрыша пользователя"""
        with self.db_session() as db:
            try:
                user_record = (db.query(TelegramUser)
                               .filter(TelegramUser.telegram_id == user_id)
                               .first())
                return user_record if user_record and user_record.defeat_coins > 0 else None
            except Exception as e:
                self.logger.error(f"Error in _get_user_loss_record: {e}")
                return None