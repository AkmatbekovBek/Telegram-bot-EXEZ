import logging
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, update, select, func, desc
from typing import Optional, List, Tuple, Dict
from datetime import datetime, date, timedelta
import database.models as models
from .models import ModerationLog, ModerationAction
from database.models import User


# Настройка логгера
logger = logging.getLogger(__name__)

class UserRepository:
    @staticmethod
    def get_or_create_user(db: Session, tg_id: int, chat_id: int, username: str = "") -> User:
        user = db.query(User).filter(
            User.tg_id == tg_id,
            User.chat_id == chat_id
        ).first()

        if not user:
            user = User(
                tg_id=tg_id,
                chat_id=chat_id,
                username=username[:32] if username else "",
                coins=0,
                win_coins=0,
                defeat_coins=0,
                max_win_coins=0,
                min_win_coins=0,
                max_bet_coins=0
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # Обновляем username, если изменился
        if username and user.username != username:
            user.username = username[:32]
            db.commit()

        return user

    @staticmethod
    def get_or_create_user(db: Session, telegram_id: int, username: str, first_name: str,
                           last_name: str = None) -> models.TelegramUser:
        # Очищаем и обрезаем данные перед сохранением
        first_name = UserRepository.clean_telegram_field(first_name, 255) if first_name else None
        last_name = UserRepository.clean_telegram_field(last_name, 255) if last_name else None
        username = UserRepository.clean_telegram_field(username, 255) if username else None

        user = db.query(models.TelegramUser).filter(models.TelegramUser.telegram_id == telegram_id).first()
        if not user:
            user = models.TelegramUser(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                coins=5000
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def clean_telegram_field(field: str, max_length: int) -> str:
        """Очищает и обрезает поле пользователя Telegram"""
        if not field:
            return field

        # Удаляем лишние пробелы
        field = ' '.join(field.split())

        # Обрезаем до максимальной длины
        if len(field) > max_length:
            field = field[:max_length]

        return field

    @staticmethod
    def update_admin_status(db: Session, telegram_id: int, is_admin: bool) -> Optional[models.TelegramUser]:
        """Обновляет статус администратора пользователя"""
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            user.is_admin = is_admin
            db.commit()
            db.refresh(user)
            print(f"✅ Обновлен статус администратора для пользователя {telegram_id}: {is_admin}")
        return user

    @staticmethod
    def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[models.TelegramUser]:
        return db.query(models.TelegramUser).filter(models.TelegramUser.telegram_id == telegram_id).first()

    @staticmethod
    def update_user_balance(db: Session, telegram_id: int, coins: int) -> Optional[models.TelegramUser]:
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            user.coins = coins
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def update_user_stats(db: Session, telegram_id: int, **kwargs) -> Optional[models.TelegramUser]:
        """
        Универсальный метод для обновления статистики пользователя.
        Принимает параметры: win_coins, defeat_coins, max_win_coins, min_win_coins, max_bet
        """
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            # Разрешенные поля для обновления
            allowed_fields = {'win_coins', 'defeat_coins', 'max_win_coins', 'min_win_coins', 'max_bet'}

            for key, value in kwargs.items():
                if key in allowed_fields and hasattr(user, key):
                    setattr(user, key, value)

            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def update_reference_link(db: Session, telegram_id: int, link: str) -> Optional[models.TelegramUser]:
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            user.reference_link = link
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def update_user_info(db: Session, telegram_id: int, **kwargs) -> Optional[models.TelegramUser]:
        """
        Обновляет информацию о пользователе
        """
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            # Обрабатываем текстовые поля (обрезаем если нужно)
            text_fields = ['username', 'first_name', 'last_name']
            for field in text_fields:
                if field in kwargs and kwargs[field] is not None:
                    kwargs[field] = UserRepository.clean_telegram_field(kwargs[field], 255)

            # Обновляем поля
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)

            db.commit()
            db.refresh(user)
            print(f"✅ Обновлена информация пользователя {telegram_id}: {list(kwargs.keys())}")
        return user

    @staticmethod
    def get_user_chats(db, user_id: int) -> List[Tuple[int, str]]:
        """Получает список чатов пользователя из UserChatSearch"""
        try:
            from database.models import UserChatSearch

            chats = db.query(UserChatSearch.chat_id, UserChatSearch.chat_title) \
                .filter(UserChatSearch.user_id == user_id) \
                .order_by(UserChatSearch.created_at.desc()) \
                .all()

            return [(chat_id, chat_title or f"Чат {chat_id}") for chat_id, chat_title in chats]
        except Exception as e:
            print(f"❌ Ошибка получения чатов пользователя {user_id}: {e}")
            return []

    @staticmethod
    def get_user_by_link(db: Session, link: str) -> Optional[models.TelegramUser]:
        return db.query(models.TelegramUser).filter(models.TelegramUser.reference_link == link).first()

    @staticmethod
    def get_all_users(db: Session) -> List[models.TelegramUser]:
        return db.query(models.TelegramUser).all()

    @staticmethod
    def search_users(db: Session, search_term: str) -> List[models.TelegramUser]:
        search_pattern = f"%{search_term}%"
        return db.query(models.TelegramUser).filter(
            or_(
                models.TelegramUser.username.like(search_pattern),
                models.TelegramUser.first_name.like(search_pattern)
            )
        ).all()

    @staticmethod
    def get_total_users_count(db: Session) -> int:
        return db.query(models.TelegramUser).count()

    @staticmethod
    def get_total_coins_sum(db: Session) -> int:
        result = db.query(func.sum(models.TelegramUser.coins)).scalar()
        return result if result else 0

    @staticmethod
    def update_max_bet(db: Session, telegram_id: int, bet_amount: int) -> Optional[models.TelegramUser]:
        """Обновляет максимальную ставку пользователя если текущая ставка больше"""
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            # Если у пользователя нет поля max_bet, создаем его
            if not hasattr(user, 'max_bet'):
                user.max_bet = 0

            # Обновляем только если текущая ставка больше предыдущего максимума
            if bet_amount > user.max_bet:
                user.max_bet = bet_amount
                db.commit()
                db.refresh(user)
                print(f"✅ Обновлена максимальная ставка для пользователя {telegram_id}: {bet_amount}")
            return user
        return None

    @staticmethod
    def create_user_safe(db: Session, telegram_id: int, first_name: str, username: str = None,
                         last_name: str = None, **kwargs) -> models.TelegramUser:
        """
        Безопасное создание пользователя с обработкой длинных полей
        """
        # Очищаем данные
        first_name = UserRepository.clean_telegram_field(first_name, 255) if first_name else None
        last_name = UserRepository.clean_telegram_field(last_name, 255) if last_name else None
        username = UserRepository.clean_telegram_field(username, 255) if username else None

        user = models.TelegramUser(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            coins=5000,
            **kwargs
        )

        try:
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"✅ Создан пользователь: {telegram_id} ({first_name or 'без имени'})")
            return user
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка создания пользователя {telegram_id}: {e}")
            # Пытаемся получить существующего пользователя
            return UserRepository.get_user_by_telegram_id(db, telegram_id)

    @staticmethod
    def get_admin_users(db: Session):
        """Получить всех администраторов"""
        return db.query(models.TelegramUser).filter(models.TelegramUser.is_admin == True).all()

    @staticmethod
    def update_admin_status(db: Session, telegram_id: int, is_admin: bool) -> Optional[models.TelegramUser]:
        """Обновляет статус администратора пользователя"""
        user = UserRepository.get_user_by_telegram_id(db, telegram_id)
        if user:
            user.is_admin = is_admin
            db.commit()
            db.refresh(user)
            print(f"✅ Обновлен статус администратора для пользователя {telegram_id}: {is_admin}")
        return user

    # Добавьте в класс UserRepository:

    @staticmethod
    def get_all_chats(db: Session) -> List[int]:
        """Получает все уникальные chat_id из таблицы UserChat"""
        try:
            # Получаем все уникальные chat_id из UserChat
            chat_ids = db.query(models.UserChat.chat_id).distinct().all()
            return [chat_id[0] for chat_id in chat_ids if chat_id[0] is not None and chat_id[0] != 0]
        except Exception as e:
            print(f"❌ Ошибка получения чатов: {e}")
            return []

    @staticmethod
    def get_active_chats(db: Session, days_active: int = 30) -> List[int]:
        """Получает активные чаты (где есть пользователи)"""
        try:
            # Простая реализация - возвращаем все чаты, где есть пользователи
            # Можно улучшить, добавив поле last_activity в модель UserChat
            chat_ids = db.query(models.UserChat.chat_id).distinct().all()
            return [chat_id[0] for chat_id in chat_ids if chat_id[0] is not None and chat_id[0] != 0]
        except Exception as e:
            print(f"❌ Ошибка получения активных чатов: {e}")
            return []

    @staticmethod
    def get_chat_members_count(db: Session, chat_id: int) -> int:
        """Получает количество участников в чате"""
        try:
            return db.query(models.UserChat).filter(
                models.UserChat.chat_id == chat_id
            ).count()
        except Exception as e:
            print(f"❌ Ошибка получения количества участников чата {chat_id}: {e}")
            return 0

    @staticmethod
    def get_chat_info(db: Session, chat_id: int) -> dict:
        """Получает информацию о чате"""
        try:
            members_count = UserRepository.get_chat_members_count(db, chat_id)

            # Получаем информацию о чате из таблицы Chat (если она существует)
            chat_info = None
            try:
                chat_info = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
            except:
                pass  # Если таблицы Chat нет, игнорируем

            # Определяем активность на основе наличия пользователей
            is_active = members_count > 0

            return {
                'chat_id': chat_id,
                'members_count': members_count,
                'title': getattr(chat_info, 'title', 'Неизвестно'),
                'chat_type': getattr(chat_info, 'chat_type', 'Неизвестно'),
                'is_active': is_active
            }
        except Exception as e:
            print(f"❌ Ошибка получения информации о чате {chat_id}: {e}")
            return {'chat_id': chat_id, 'members_count': 0, 'title': 'Неизвестно', 'is_active': False}

    @staticmethod
    def get_user_chats(db, user_id: int) -> List[Tuple[int, str]]:
        """Получает список чатов, где находится пользователь"""
        try:
            from database.models import UserChatSearch

            chats = db.query(UserChatSearch.chat_id, UserChatSearch.chat_title) \
                .filter(UserChatSearch.user_id == user_id) \
                .order_by(UserChatSearch.created_at.desc()) \
                .all()
            return [(chat_id, chat_title) for chat_id, chat_title in chats]
        except Exception as e:
            logger.error(f"Error getting user chats for {user_id}: {e}")
            return []


# Остальные классы остаются без изменений...

class ReferenceRepository:
    @staticmethod
    def add_reference(db: Session, owner_telegram_id: int, reference_telegram_id: int) -> models.ReferenceUser:
        reference = models.ReferenceUser(
            owner_telegram_id=owner_telegram_id,
            reference_telegram_id=reference_telegram_id
        )
        db.add(reference)
        db.commit()
        db.refresh(reference)
        return reference

    @staticmethod
    def get_referrals_count(db: Session, user_id: int) -> int:
        """Получает количество рефералов пользователя"""
        try:
            # ИСПРАВЛЕНИЕ: Используем правильную модель и поле
            count = db.query(models.ReferenceUser).filter(
                models.ReferenceUser.owner_telegram_id == user_id
            ).count()
            return count
        except Exception as e:
            print(f"❌ Ошибка получения количества рефералов: {e}")
            return 0

    @staticmethod
    def check_reference_exists(db: Session, reference_telegram_id: int) -> bool:
        return db.query(models.ReferenceUser).filter(
            models.ReferenceUser.reference_telegram_id == reference_telegram_id
        ).first() is not None

    @staticmethod
    def get_user_references(db: Session, owner_telegram_id: int) -> List[models.ReferenceUser]:
        return db.query(models.ReferenceUser).filter(
            models.ReferenceUser.owner_telegram_id == owner_telegram_id
        ).all()




class TransactionRepository:
    @staticmethod
    def create_transaction(db: Session, from_user_id: int, to_user_id: int, amount: int,
                           description: str = "") -> models.Transaction:
        transaction = models.Transaction(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            amount=amount,
            description=description
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        return transaction

    @staticmethod
    def get_user_transactions(db: Session, user_id: int, limit: int = 10) -> List[models.Transaction]:
        return db.query(models.Transaction).filter(
            or_(
                models.Transaction.from_user_id == user_id,
                models.Transaction.to_user_id == user_id
            )
        ).order_by(desc(models.Transaction.timestamp)).limit(limit).all()


class ChatRepository:
    staticmethod

    def add_user_to_chat(db: Session, user_id: int, chat_id: int, username: str = None,
                         first_name: str = None) -> models.UserChat:
        """Добавляет пользователя в чат, если его там еще нет, с автоматической регистрацией"""
        try:
            # Сначала проверяем, существует ли пользователь
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                # Автоматически создаем пользователя
                user = UserRepository.create_user_safe(
                    db, user_id,
                    first_name=first_name or "Пользователь",
                    username=username
                )

            # Проверяем, существует ли уже запись в чате
            existing = db.query(models.UserChat).filter_by(
                user_id=user_id,
                chat_id=chat_id
            ).first()

            if existing:
                return existing

            # Создаем новую запись
            user_chat = models.UserChat(user_id=user_id, chat_id=chat_id)
            db.add(user_chat)
            db.commit()
            db.refresh(user_chat)
            print(f"✅ Пользователь {user_id} добавлен в чат {chat_id}")
            return user_chat

        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка добавления пользователя в чат: {e}")
            # Пытаемся вернуть существующую запись при ошибке
            existing = db.query(models.UserChat).filter_by(
                user_id=user_id,
                chat_id=chat_id
            ).first()
            return existing

    @staticmethod
    def get_chat_users_count(db: Session, chat_id: int) -> int:
        return db.query(models.UserChat).filter(models.UserChat.chat_id == chat_id).count()

    @staticmethod
    def get_top_rich_in_chat(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, str, int]]:
        """Получает топ богатеев в чате без дубликатов"""
        try:
            # Используем DISTINCT для устранения дубликатов
            from sqlalchemy import distinct

            # Сначала получаем уникальные user_id из чата
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            # Затем получаем данные пользователей
            results = db.query(
                models.TelegramUser.telegram_id,  # Добавляем telegram_id
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.coins
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).order_by(
                desc(models.TelegramUser.coins)
            ).limit(limit).all()

            return [(telegram_id, username or "", first_name or "", coins) for telegram_id, username, first_name, coins
                    in results]

        except Exception as e:
            print(f"❌ Ошибка получения топа богатеев: {e}")
            return []

    @staticmethod
    def get_user_rank_in_chat(db: Session, chat_id: int, user_id: int) -> Optional[int]:
        # Создаем подзапрос для ранжирования пользователей в чате
        subquery = db.query(
            models.TelegramUser.telegram_id,
            func.row_number().over(
                order_by=desc(models.TelegramUser.coins)
            ).label('position')
        ).join(
            models.UserChat,
            models.TelegramUser.telegram_id == models.UserChat.user_id
        ).filter(
            models.UserChat.chat_id == chat_id
        ).subquery()

        result = db.query(subquery.c.position).filter(
            subquery.c.telegram_id == user_id
        ).first()

        return result[0] if result else None

    @staticmethod
    def get_top_wins(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по выигранным ставкам в чате"""
        try:
            # Сначала получаем уникальные user_id из чата
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            # Затем получаем топ по выигрышам
            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.win_coins
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).filter(
                models.TelegramUser.win_coins > 0
            ).order_by(
                desc(models.TelegramUser.win_coins)
            ).limit(limit).all()

            return [(telegram_id, first_name or username or "ㅤ", win_coins)
                    for telegram_id, username, first_name, win_coins in results]

        except Exception as e:
            print(f"❌ Ошибка получения топа выигрышей: {e}")
            return []

    @staticmethod
    def get_top_losses(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по проигранным ставкам в чате"""
        try:
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.defeat_coins
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).filter(
                models.TelegramUser.defeat_coins > 0
            ).order_by(
                desc(models.TelegramUser.defeat_coins)
            ).limit(limit).all()

            return [(telegram_id, first_name or username or "ㅤ", defeat_coins)
                    for telegram_id, username, first_name, defeat_coins in results]

        except Exception as e:
            print(f"❌ Ошибка получения топа проигрышей: {e}")
            return []

    @staticmethod
    def get_top_max_win(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по максимальному выигрышу в чате"""
        try:
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.max_win_coins
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).filter(
                models.TelegramUser.max_win_coins > 0
            ).order_by(
                desc(models.TelegramUser.max_win_coins)
            ).limit(limit).all()

            return [(telegram_id, first_name or username or "ㅤ", max_win_coins)
                    for telegram_id, username, first_name, max_win_coins in results]

        except Exception as e:
            print(f"❌ Ошибка получения топа максимальных выигрышей: {e}")
            return []

    @staticmethod
    def get_top_max_loss(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по максимальному проигрышу в чате (из RouletteTransaction)"""
        try:
            # Сначала получаем уникальные user_id из чата
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            # Получаем максимальные проигрыши из RouletteTransaction
            results = db.query(
                models.RouletteTransaction.user_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                func.min(models.RouletteTransaction.profit).label('max_loss')
            ).join(
                user_ids_subquery,
                models.RouletteTransaction.user_id == user_ids_subquery.c.user_id
            ).join(
                models.TelegramUser,
                models.RouletteTransaction.user_id == models.TelegramUser.telegram_id
            ).filter(
                models.RouletteTransaction.profit < 0  # Только проигрыши
            ).group_by(
                models.RouletteTransaction.user_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name
            ).order_by(
                func.min(models.RouletteTransaction.profit)
                # Сортируем по возрастанию (самые большие по модулю проигрыши)
            ).limit(limit).all()

            # Преобразуем отрицательные значения в положительные для отображения
            return [(user_id, first_name or username or "ㅤ", abs(max_loss))
                    for user_id, username, first_name, max_loss in results]

        except Exception as e:
            print(f"❌ Ошибка получения топа максимальных проигрышей: {e}")
            return []

    @staticmethod
    def get_top_max_bet(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Топ по максимальной ставке в чате"""
        try:
            user_ids_subquery = db.query(
                models.UserChat.user_id
            ).filter(
                models.UserChat.chat_id == chat_id
            ).distinct().subquery()

            results = db.query(
                models.TelegramUser.telegram_id,
                models.TelegramUser.username,
                models.TelegramUser.first_name,
                models.TelegramUser.max_bet
            ).join(
                user_ids_subquery,
                models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
            ).filter(
                models.TelegramUser.max_bet > 0
            ).order_by(
                desc(models.TelegramUser.max_bet)
            ).limit(limit).all()

            return [(telegram_id, first_name or username or "ㅤ", max_bet)
                    for telegram_id, username, first_name, max_bet in results]

        except Exception as e:
            print(f"❌ Ошибка получения топа максимальных ставок: {e}")
            return []

    @staticmethod
    def get_user_stats_rank(db: Session, chat_id: int, user_id: int, stat_type: str) -> Optional[int]:
        """Позиция пользователя в статистике по определенному типу"""
        try:
            if stat_type == "max_loss":
                # Для максимального проигрыша используем данные из RouletteTransaction
                user_ids_subquery = db.query(
                    models.UserChat.user_id
                ).filter(
                    models.UserChat.chat_id == chat_id
                ).distinct().subquery()

                # Создаем подзапрос с ранжированием по максимальным проигрышам
                subquery = db.query(
                    models.RouletteTransaction.user_id,
                    func.min(models.RouletteTransaction.profit).label('max_loss'),
                    func.row_number().over(
                        order_by=func.min(models.RouletteTransaction.profit)
                    ).label('position')
                ).join(
                    user_ids_subquery,
                    models.RouletteTransaction.user_id == user_ids_subquery.c.user_id
                ).filter(
                    models.RouletteTransaction.profit < 0
                ).group_by(models.RouletteTransaction.user_id).subquery()

                result = db.query(subquery.c.position).filter(
                    subquery.c.user_id == user_id
                ).first()

                return result[0] if result else None

            else:
                # Для других типов статистики используем существующую логику
                user_ids_subquery = db.query(
                    models.UserChat.user_id
                ).filter(
                    models.UserChat.chat_id == chat_id
                ).distinct().subquery()

                stat_fields = {
                    'wins': models.TelegramUser.win_coins,
                    'losses': models.TelegramUser.defeat_coins,
                    'max_win': models.TelegramUser.max_win_coins,
                    'max_bet': models.TelegramUser.max_bet
                }

                if stat_type not in stat_fields:
                    return None

                stat_field = stat_fields[stat_type]

                subquery = db.query(
                    models.TelegramUser.telegram_id,
                    func.row_number().over(
                        order_by=desc(stat_field)
                    ).label('position')
                ).join(
                    user_ids_subquery,
                    models.TelegramUser.telegram_id == user_ids_subquery.c.user_id
                ).filter(
                    stat_field > 0
                ).subquery()

                result = db.query(subquery.c.position).filter(
                    subquery.c.telegram_id == user_id
                ).first()

                return result[0] if result else None

        except Exception as e:
            print(f"❌ Ошибка получения позиции пользователя в статистике: {e}")
            return None

    @staticmethod
    def get_user_stats(db: Session, user_id: int, stat_type: str) -> Optional[int]:
        """Статистика пользователя по определенному типу"""
        try:
            if stat_type == "max_loss":
                # Для максимального проигрыша используем данные из RouletteTransaction
                result = db.query(
                    func.min(models.RouletteTransaction.profit)
                ).filter(
                    models.RouletteTransaction.user_id == user_id,
                    models.RouletteTransaction.profit < 0
                ).scalar()

                print(f"🔍 get_user_stats max_loss для {user_id}: raw_result={result}")

                if result is not None:
                    abs_result = abs(result)
                    print(f"🔍 get_user_stats max_loss для {user_id}: absolute_value={abs_result}")
                    return abs_result
                else:
                    print(f"🔍 get_user_stats max_loss для {user_id}: нет данных")
                    return 0

            else:
                # Для других типов статистики используем существующую логику
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    return None

                stat_values = {
                    'wins': user.win_coins,
                    'losses': user.defeat_coins,
                    'max_win': user.max_win_coins,
                    'max_bet': user.max_bet
                }

                return stat_values.get(stat_type)

        except Exception as e:
            print(f"❌ Ошибка получения статистики пользователя: {e}")
            return None

    @staticmethod
    def check_user_losses(db: Session, user_id: int):
        """Проверяет проигрыши конкретного пользователя"""
        user_losses = db.query(models.RouletteTransaction).filter(
            models.RouletteTransaction.user_id == user_id,
            models.RouletteTransaction.profit < 0
        ).all()

        print(f"🔍 Проигрыши пользователя {user_id}: {len(user_losses)} записей")

        if user_losses:
            max_loss = min([loss.profit for loss in user_losses])
            print(f"🔍 Максимальный проигрыш: {max_loss} (абсолютное значение: {abs(max_loss)})")

        return len(user_losses)

    # Добавьте этот метод для отладки
    @staticmethod
    def debug_max_loss_data(db: Session, chat_id: int):
        """Отладочный метод для проверки данных о проигрышах"""
        print("🔍 Проверка данных для максимальных проигрышей:")

        # Проверяем DailyRecord
        daily_records = db.query(models.DailyRecord).filter(
            models.DailyRecord.amount < 0
        ).all()
        print(f"📊 DailyRecord с отрицательными значениями: {len(daily_records)}")

        # Проверяем RouletteTransaction
        roulette_losses = db.query(models.RouletteTransaction).filter(
            models.RouletteTransaction.profit < 0
        ).all()
        print(f"🎰 RouletteTransaction с проигрышами: {len(roulette_losses)}")

        # Проверяем пользователей чата
        chat_users = db.query(models.UserChat.user_id).filter(
            models.UserChat.chat_id == chat_id
        ).distinct().all()
        print(f"👥 Пользователей в чате: {len(chat_users)}")

        return {
            'daily_records_negative': len(daily_records),
            'roulette_losses': len(roulette_losses),
            'chat_users': len(chat_users)
        }



class DailyRecordRepository:
    @staticmethod
    def add_or_update_daily_record(db, user_id: int, username: str, first_name: str, amount: int, chat_id: int = 0):
        from datetime import date
        from database.models import DailyRecord

        today = date.today()

        # Ищем существующую запись за сегодня
        existing_record = db.query(DailyRecord).filter(
            DailyRecord.user_id == user_id,
            DailyRecord.record_date == today,
            DailyRecord.chat_id == chat_id
        ).first()

        if existing_record:
            # Обновляем если новый рекорд больше
            if amount > existing_record.amount:
                existing_record.amount = amount
                existing_record.username = username
                existing_record.first_name = first_name
                db.commit()
                return existing_record
            return existing_record
        else:
            # Создаем новую запись
            new_record = DailyRecord(
                user_id=user_id,
                username=username,
                first_name=first_name,
                amount=amount,
                record_date=today,
                chat_id=chat_id
            )
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            return new_record

    @staticmethod
    def get_top3_today(db: Session, chat_id: int) -> List[Tuple[int, str, int]]:
        today = date.today()
        results = db.query(
            models.DailyRecord.user_id,  # Добавляем user_id
            models.DailyRecord.username,
            models.DailyRecord.first_name,
            models.DailyRecord.amount
        ).filter(
            models.DailyRecord.record_date == today,
            models.DailyRecord.chat_id == chat_id
        ).order_by(
            desc(models.DailyRecord.amount)
        ).limit(3).all()

        top_scores = []
        for user_id, username, first_name, amount in results:
            display_name = first_name if first_name else username
            top_scores.append((user_id, display_name, amount))

        return top_scores

    @staticmethod
    def get_top_today(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Получает топ рекордов за сегодня с динамическим лимитом"""
        today = date.today()
        results = db.query(
            models.DailyRecord.user_id,
            models.DailyRecord.username,
            models.DailyRecord.first_name,
            models.DailyRecord.amount
        ).filter(
            models.DailyRecord.record_date == today,
            models.DailyRecord.chat_id == chat_id
        ).order_by(
            desc(models.DailyRecord.amount)
        ).limit(limit).all()

        top_scores = []
        for user_id, username, first_name, amount in results:
            display_name = first_name if first_name else username
            top_scores.append((user_id, display_name, amount))

        return top_scores

    @staticmethod
    def get_user_rank_today(db: Session, chat_id: int, user_id: int) -> Optional[int]:
        """Позиция пользователя в рекордах за сегодня"""
        today = date.today()

        # Создаем подзапрос для ранжирования
        subquery = db.query(
            models.DailyRecord.user_id,
            func.row_number().over(
                order_by=desc(models.DailyRecord.amount)
            ).label('position')
        ).filter(
            models.DailyRecord.record_date == today,
            models.DailyRecord.chat_id == chat_id
        ).subquery()

        result = db.query(subquery.c.position).filter(
            subquery.c.user_id == user_id
        ).first()

        return result[0] if result else None

    @staticmethod
    def get_user_daily_record_in_chat(db: Session, user_id: int, chat_id: int):
        """Получает рекорд пользователя за сегодня в конкретном чате"""
        today = date.today()
        return db.query(models.DailyRecord).filter(
            models.DailyRecord.user_id == user_id,
            models.DailyRecord.record_date == today,
            models.DailyRecord.chat_id == chat_id
        ).first()

    @staticmethod
    def add_or_update_daily_loss_record(db, user_id: int, username: str, first_name: str, loss_amount: int,
                                        chat_id: int = 0):
        """Добавляет или обновляет рекорд проигрыша за день"""
        from datetime import date
        from database.models import DailyLossRecord

        today = date.today()

        # Ищем существующую запись за сегодня
        existing_record = db.query(DailyLossRecord).filter(
            DailyLossRecord.user_id == user_id,
            DailyLossRecord.record_date == today,
            DailyLossRecord.chat_id == chat_id
        ).first()

        if existing_record:
            # Обновляем если новый рекорд больше (больший проигрыш)
            if loss_amount > existing_record.amount:
                existing_record.amount = loss_amount
                existing_record.username = username
                existing_record.first_name = first_name
                db.commit()
                return existing_record
            return existing_record
        else:
            # Создаем новую запись
            new_record = DailyLossRecord(
                user_id=user_id,
                username=username,
                first_name=first_name,
                amount=loss_amount,
                record_date=today,
                chat_id=chat_id
            )
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            return new_record

    @staticmethod
    def get_top_losses_today(db: Session, chat_id: int, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Получает топ рекордов проигрышей за сегодня"""
        from database.models import DailyLossRecord
        today = date.today()

        results = db.query(
            DailyLossRecord.user_id,
            DailyLossRecord.username,
            DailyLossRecord.first_name,
            DailyLossRecord.amount
        ).filter(
            DailyLossRecord.record_date == today,
            DailyLossRecord.chat_id == chat_id
        ).order_by(
            desc(DailyLossRecord.amount)
        ).limit(limit).all()

        top_losses = []
        for user_id, username, first_name, amount in results:
            display_name = first_name if first_name else username
            top_losses.append((user_id, display_name, amount))

        return top_losses


class RouletteRepository:
    @staticmethod
    def create_roulette_transaction(db: Session, user_id: int, amount: int, is_win: bool,
                                    bet_type: str = None, bet_value: str = None,
                                    result_number: int = None, profit: int = None,
                                    created_at: datetime = None) -> models.RouletteTransaction:
        if profit is None:
            profit = amount if is_win else -amount

        # Округляем время до секунд для группировки
        if created_at:
            created_at = created_at.replace(microsecond=0)

        transaction = models.RouletteTransaction(
            user_id=user_id,
            amount=amount,
            is_win=is_win,
            bet_type=bet_type,
            bet_value=bet_value,
            result_number=result_number,
            profit=profit,
            created_at=created_at or datetime.now().replace(microsecond=0)  # Округляем время
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        return transaction

    @staticmethod
    def generate_game_session_id() -> str:
        """Генерирует уникальный ID для игровой сессии"""
        import uuid
        from datetime import datetime
        return f"game_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def get_grouped_bet_history(db: Session, user_id: int, limit: int = 12) -> List[Dict]:
        """Получает сгруппированную историю ставок по сессиям"""
        try:
            # Получаем все транзакции пользователя
            from sqlalchemy import desc

            transactions = db.query(models.RouletteTransaction).filter(
                models.RouletteTransaction.user_id == user_id
            ).order_by(desc(models.RouletteTransaction.created_at)).limit(50).all()

            if not transactions:
                return []

            # Группируем по game_session_id
            sessions_dict = {}
            for trans in transactions:
                session_id = trans.game_session_id or "no_session"

                if session_id not in sessions_dict:
                    sessions_dict[session_id] = {
                        'transactions': [],
                        'total_amount': 0,
                        'total_profit': 0,
                        'last_time': trans.created_at
                    }

                sessions_dict[session_id]['transactions'].append(trans)
                sessions_dict[session_id]['total_amount'] += int(trans.amount)

                # Рассчитываем чистую прибыль
                profit = 0
                if hasattr(trans, 'profit') and trans.profit is not None:
                    profit = int(trans.profit)
                elif trans.is_win:
                    profit = int(trans.amount)
                else:
                    profit = -int(trans.amount)

                sessions_dict[session_id]['total_profit'] += profit

            # Формируем результат
            grouped_results = []
            for session_id, session_data in sessions_dict.items():
                if session_data['transactions']:
                    # Сортируем транзакции внутри сессии по времени
                    session_data['transactions'].sort(key=lambda x: x.created_at)
                    grouped_results.append({
                        'session_id': session_id,
                        'transactions': session_data['transactions'],
                        'total_amount': session_data['total_amount'],
                        'total_profit': session_data['total_profit'],
                        'bet_count': len(session_data['transactions']),
                        'last_time': session_data['last_time']
                    })

            # Сортируем сессии по времени (от новых к старым)
            grouped_results.sort(key=lambda x: x['last_time'], reverse=True)

            return grouped_results[:limit]

        except Exception as e:
            print(f"Ошибка при группировке истории: {e}")
            return []

    @staticmethod
    def get_user_bet_history(db: Session, user_id: int, limit: int = 10) -> List[models.RouletteTransaction]:
        return db.query(models.RouletteTransaction).filter(
            models.RouletteTransaction.user_id == user_id
        ).order_by(desc(models.RouletteTransaction.created_at)).limit(limit).all()

    @staticmethod
    def add_game_log(db: Session, chat_id: int, result: int, color_emoji: str) -> models.RouletteGameLog:
        log = models.RouletteGameLog(
            chat_id=chat_id,
            result=result,
            color_emoji=color_emoji
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_recent_game_logs(db: Session, chat_id: int, limit: int = 10) -> List[models.RouletteGameLog]:
        return db.query(models.RouletteGameLog).filter(
            models.RouletteGameLog.chat_id == chat_id
        ).order_by(desc(models.RouletteGameLog.created_at)).limit(limit).all()

    @staticmethod
    def get_user_recent_bets(db: Session, user_id: int, limit: int = 5) -> List:
        """Получает последние ставки пользователя"""
        try:
            bets = db.query(models.RouletteTransaction).filter(
                models.RouletteTransaction.user_id == user_id
            ).order_by(
                desc(models.RouletteTransaction.created_at)
            ).limit(limit).all()
            return bets
        except Exception as e:
            print(f"❌ Ошибка получения истории ставок: {e}")
            return []


class ShopRepository:
    @staticmethod
    def add_user_purchase(db: Session, user_id: int, item_id: int, item_name: str, price: int,
                          chat_id: int = -1, duration_days: int = 0):
        """Добавить покупку с возможностью указать срок действия"""
        from datetime import datetime, timedelta

        # thief(1) и police(2) всегда выдаём на 28 дней (даже если duration_days забыли передать)
        if item_id in (1, 2) and duration_days <= 0:
            duration_days = 28

        expires_at = None
        if duration_days > 0:
            expires_at = datetime.now() + timedelta(days=duration_days)

        # Используем прямую модель UserPurchase с правильными названиями полей
        purchase = models.UserPurchase(
            user_id=user_id,
            item_id=item_id,
            item_name=item_name,
            price=price,
            chat_id=chat_id,
            purchased_at=datetime.now(),
            expires_at=expires_at
        )

        db.add(purchase)
        db.commit()
        db.refresh(purchase)
        return purchase

    @staticmethod
    def has_user_purchased_in_chat(db: Session, user_id: int, item_id: int, chat_id: int) -> bool:
        """Проверяет, купил ли пользователь товар в конкретном чате"""
        purchase = db.query(models.UserPurchase).filter(
            models.UserPurchase.user_id == user_id,
            models.UserPurchase.item_id == item_id,
            models.UserPurchase.chat_id == chat_id
        ).first()

        if not purchase:
            return False

        # Проверяем срок действия если есть
        if purchase.expires_at:
            return purchase.expires_at > datetime.now()

        return True

    @staticmethod
    def get_user_purchases_in_chat(db: Session, user_id: int, chat_id: int) -> list:
        """Получает список ID АКТИВНЫХ товаров, купленных пользователем в конкретном чате"""
        try:
            purchases = db.query(models.UserPurchase).filter(
                models.UserPurchase.user_id == user_id,
                models.UserPurchase.chat_id == chat_id
            ).all()

            now = datetime.now()
            ids = []
            for purchase in purchases:
                if ShopRepository._is_purchase_active(purchase, now):
                    ids.append(purchase.item_id)

            # Убираем дубликаты, сохраняя порядок
            seen = set()
            result = []
            for pid in ids:
                if pid not in seen:
                    seen.add(pid)
                    result.append(pid)

            return result

        except Exception as e:
            print(f"❌ Ошибка получения покупок в чате: {e}")
            return []

    @staticmethod
    def get_user_purchases(db: Session, user_id: int, chat_id: int = None) -> list:
        """
        Получает список ID АКТИВНЫХ товаров, купленных пользователем.

        Важно: истекшие привилегии (в т.ч. thief/police) сюда не попадают,
        чтобы они автоматически "снимались" с профиля.
        """
        try:
            query = db.query(models.UserPurchase).filter(models.UserPurchase.user_id == user_id)
            if chat_id is not None:
                query = query.filter(models.UserPurchase.chat_id == chat_id)

            purchases = query.all()
            now = datetime.now()

            ids = []
            for purchase in purchases:
                if ShopRepository._is_purchase_active(purchase, now):
                    ids.append(purchase.item_id)

            # Убираем дубликаты, сохраняя порядок
            seen = set()
            result = []
            for pid in ids:
                if pid not in seen:
                    seen.add(pid)
                    result.append(pid)

            return result

        except Exception as e:
            print(f"❌ Ошибка получения покупок пользователя: {e}")
            return []

    @staticmethod
    def get_user_purchases_with_details(db, user_id: int):
        """Получить все покупки пользователя с деталями"""
        try:
            purchases = db.query(models.UserPurchase).filter(
                models.UserPurchase.user_id == user_id
            ).all()
            return purchases
        except Exception as e:
            print(f"❌ Ошибка получения покупок: {e}")
            return []

    @staticmethod
    def remove_user_purchase(db, user_id: int, item_id: int):
        """Удалить покупку пользователя"""
        try:
            result = db.query(models.UserPurchase).filter(
                models.UserPurchase.user_id == user_id,
                models.UserPurchase.item_id == item_id
            ).delete()
            db.commit()
            return result > 0
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка удаления покупки: {e}")
            return False

    @staticmethod
    def extend_user_purchase(db, user_id: int, item_id: int, days: int):
        """Продлить покупку пользователя"""
        purchase = db.query(models.UserPurchase).filter(
            models.UserPurchase.user_id == user_id,
            models.UserPurchase.item_id == item_id
        ).first()

        if purchase and purchase.expires_at:
            from datetime import datetime, timedelta
            # Если срок истек, устанавливаем от текущей даты
            if purchase.expires_at < datetime.now():
                purchase.expires_at = datetime.now() + timedelta(days=days)
            else:
                purchase.expires_at += timedelta(days=days)
            db.commit()
            return True
        return False


    @staticmethod
    def _is_purchase_active(purchase, now: datetime = None) -> bool:
        """
        Возвращает True, если покупка активна.

        ВАЖНО: для привилегий thief(1) и police(2) срок должен быть 28 дней.
        Если expires_at не заполнен (старые записи) — считаем срок от purchased_at.
        """
        now = now or datetime.now()

        try:
            expires_at = getattr(purchase, "expires_at", None)
            if expires_at:
                return expires_at > now

            item_id = getattr(purchase, "item_id", None)

            # thief / police: 28 дней даже если expires_at пустой
            if item_id in (1, 2):
                purchased_at = getattr(purchase, "purchased_at", None)
                if purchased_at:
                    return purchased_at + timedelta(days=28) > now
                # если даты нет — считаем неактивной (безопаснее)
                return False

            # остальные покупки без expires_at считаем бессрочными
            return True
        except Exception:
            return False

    @staticmethod
    def has_active_purchase(db: Session, user_id: int, item_id: int, chat_id: int = None) -> bool:
        """
        Проверяет, есть ли у пользователя активная покупка (учитывает expires_at).
        Для thief(1) и police(2) также учитывает 28 дней от purchased_at, если expires_at пустой.
        """
        try:
            query = db.query(models.UserPurchase).filter(
                models.UserPurchase.user_id == user_id,
                models.UserPurchase.item_id == item_id
            )
            if chat_id is not None:
                query = query.filter(models.UserPurchase.chat_id == chat_id)

            purchases = query.all()
            if not purchases:
                return False

            now = datetime.now()
            return any(ShopRepository._is_purchase_active(p, now) for p in purchases)

        except Exception as e:
            print(f"❌ Ошибка проверки активной покупки: {e}")
            return False

    @staticmethod
    def get_active_purchases(db: Session, user_id: int) -> list:
        """
        Получает список ID АКТИВНЫХ товаров, купленных пользователем (учитывает expires_at).

        Важно: истекшие привилегии автоматически не возвращаются (т.е. "сняты" с профиля).
        """
        try:
            purchases = db.query(models.UserPurchase).filter(
                models.UserPurchase.user_id == user_id
            ).all()

            now = datetime.now()
            active_ids = []
            for purchase in purchases:
                if ShopRepository._is_purchase_active(purchase, now):
                    active_ids.append(purchase.item_id)

            # unique preserving order
            seen = set()
            result = []
            for pid in active_ids:
                if pid not in seen:
                    seen.add(pid)
                    result.append(pid)

            return result

        except Exception as e:
            print(f"❌ Ошибка получения активных покупок: {e}")
            return []

    @staticmethod
    def cleanup_expired_purchases(db):
        """Очищает истекшие покупки"""
        try:
            expired_count = db.query(models.UserPurchase).filter(
                models.UserPurchase.expires_at <= datetime.now()
            ).delete()
            db.commit()
            return expired_count
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка очистки истекших покупок: {e}")
            return 0


class TransferLimitRepository:
    @staticmethod
    def add_transfer_limit(db: Session, user_id: int, amount: int, transfer_time: datetime) -> models.TransferLimit:
        limit = models.TransferLimit(
            user_id=user_id,
            amount=amount,
            transfer_time=transfer_time
        )
        db.add(limit)
        db.commit()
        db.refresh(limit)
        return limit

    @staticmethod
    def get_user_transfers_last_6h(db: Session, user_id: int) -> List[models.TransferLimit]:
        six_hours_ago = datetime.now() - timedelta(hours=6)
        return db.query(models.TransferLimit).filter(
            models.TransferLimit.user_id == user_id,
            models.TransferLimit.transfer_time >= six_hours_ago
        ).order_by(desc(models.TransferLimit.transfer_time)).all()

    @staticmethod
    def clean_old_transfers(db: Session):
        seven_days_ago = datetime.now() - timedelta(days=1)
        deleted_count = db.query(models.TransferLimit).filter(
            models.TransferLimit.transfer_time < seven_days_ago
        ).delete()
        db.commit()
        return deleted_count

    @staticmethod
    def clean_daily_old_data(db: Session):
        """Ежедневная очистка старых данных (вызывать каждый день в 00:00)"""
        deleted_data = {}

        # 1. Очищаем трансферы старше 7 дней
        deleted_data['transfers'] = TransferLimitRepository.clean_old_transfers(db)

        # 2. Очищаем старые лимиты рулетки (старше 7 дней)
        deleted_data['roulette_limits'] = RouletteLimitRepository.cleanup_old_limits(db)

        # 3. Очищаем старые транзакции (старше 30 дней)
        thirty_days_ago = datetime.now() - timedelta(days=3)
        deleted_data['transactions'] = db.query(models.Transaction).filter(
            models.Transaction.timestamp < thirty_days_ago
        ).delete()

        # 4. Очищаем старые ставки в рулетке (старше 30 дней)
        deleted_data['roulette_bets'] = db.query(models.RouletteTransaction).filter(
            models.RouletteTransaction.created_at < thirty_days_ago
        ).delete()

        # 5. Очищаем старые логи игр (старше 14 дней)
        fourteen_days_ago = datetime.now() - timedelta(days=1)
        deleted_data['game_logs'] = db.query(models.RouletteGameLog).filter(
            models.RouletteGameLog.created_at < fourteen_days_ago
        ).delete()

        # 6. Очищаем старые ежедневные рекорды (старше 7 дней)
        seven_days_ago = date.today() - timedelta(days=3)
        deleted_data['daily_records'] = db.query(models.DailyRecord).filter(
            models.DailyRecord.record_date < seven_days_ago
        ).delete()

        db.commit()

        print(f"✅ Ежедневная очистка завершена. Удалено: {deleted_data}")
        return deleted_data


class GiftRepository:
    @staticmethod
    def get_all_gifts(db: Session):
        return db.query(models.Gift).filter(models.Gift.is_active == True).all()

    @staticmethod
    def get_gift_by_id(db: Session, gift_id: int):
        return db.query(models.Gift).filter(models.Gift.id == gift_id, models.Gift.is_active == True).first()

    @staticmethod
    def get_gift_by_name(db: Session, name: str):
        return db.query(models.Gift).filter(
            models.Gift.name.ilike(name),
            models.Gift.is_active == True
        ).first()

    @staticmethod
    def create_gift(db: Session, name: str, sticker: str, price: int, compliment: str):
        gift = models.Gift(
            name=name,
            sticker=sticker,
            price=price,
            compliment=compliment,
            is_active=True
        )
        db.add(gift)
        db.commit()
        db.refresh(gift)
        return gift

    @staticmethod
    def update_gift(db: Session, gift_id: int, **kwargs):
        gift = db.query(models.Gift).filter(models.Gift.id == gift_id).first()
        if gift:
            for key, value in kwargs.items():
                setattr(gift, key, value)
            db.commit()
            db.refresh(gift)
        return gift

    @staticmethod
    def delete_gift(db: Session, gift_id: int):
        gift = db.query(models.Gift).filter(models.Gift.id == gift_id).first()
        if gift:
            # Мягкое удаление
            gift.is_active = False
            db.commit()
        return gift

    @staticmethod
    def add_gift_to_user(db: Session, user_id: int, gift_id: int, quantity: int = 1):
        # user_id здесь должен быть telegram_id (BigInteger)
        user_gift = db.query(models.UserGift).filter(
            models.UserGift.user_id == user_id,  # Это telegram_id
            models.UserGift.gift_id == gift_id
        ).first()

        if user_gift:
            user_gift.quantity += quantity
        else:
            user_gift = models.UserGift(user_id=user_id, gift_id=gift_id, quantity=quantity)
            db.add(user_gift)

        db.commit()
        return user_gift

    @staticmethod
    def get_user_gifts(db: Session, user_id: int):
        # user_id здесь должен быть telegram_id
        return db.query(models.UserGift).filter(models.UserGift.user_id == user_id).all()

    @staticmethod
    def get_user_gift_by_name(db: Session, user_id: int, gift_name: str):
        # user_id здесь должен быть telegram_id
        return db.query(models.UserGift).join(models.Gift).filter(
            models.UserGift.user_id == user_id,  # Это telegram_id
            models.Gift.name.ilike(gift_name),
            models.Gift.is_active == True
        ).first()

    @staticmethod
    def remove_gift_from_user(db: Session, user_id: int, gift_id: int, quantity: int = 1):
        # user_id здесь должен быть telegram_id
        user_gift = db.query(models.UserGift).filter(
            models.UserGift.user_id == user_id,  # Это telegram_id
            models.UserGift.gift_id == gift_id
        ).first()

        if user_gift:
            if user_gift.quantity <= quantity:
                db.delete(user_gift)
            else:
                user_gift.quantity -= quantity
            db.commit()
            return True
        return False

    @staticmethod
    def get_user_gift_count(db: Session, user_id: int, gift_id: int):
        user_gift = db.query(models.UserGift).filter(
            models.UserGift.user_id == user_id,
            models.UserGift.gift_id == gift_id
        ).first()
        return user_gift.quantity if user_gift else 0


class RouletteLimitRepository:
    @staticmethod
    def get_or_create_limit(db: Session, user_id: int, chat_id: int, target_date: date = None) -> models.RouletteLimit:
        """Получает или создает запись лимита для пользователя в конкретном чате"""
        if target_date is None:
            target_date = date.today()

        # Сначала пытаемся найти существующую запись
        limit = db.query(models.RouletteLimit).filter(
            models.RouletteLimit.user_id == user_id,
            models.RouletteLimit.chat_id == chat_id,
            models.RouletteLimit.date == target_date
        ).first()

        if not limit:
            try:
                # Создаем новую запись
                limit = models.RouletteLimit(
                    user_id=user_id,
                    chat_id=chat_id,
                    date=target_date,
                    spin_count=0
                )
                db.add(limit)
                db.commit()
                db.refresh(limit)
                print(f"✅ Создана новая запись лимита для user_id={user_id}, chat_id={chat_id}, date={target_date}")
            except Exception as e:
                db.rollback()
                # Если произошла ошибка (например, запись уже существует), пытаемся снова найти
                print(f"⚠️ Ошибка создания записи, пытаемся найти существующую: {e}")
                limit = db.query(models.RouletteLimit).filter(
                    models.RouletteLimit.user_id == user_id,
                    models.RouletteLimit.chat_id == chat_id,
                    models.RouletteLimit.date == target_date
                ).first()
                if limit:
                    print(f"✅ Найдена существующая запись после ошибки создания")

        return limit

    @staticmethod
    def increment_spin_count(db: Session, user_id: int, chat_id: int) -> bool:
        """Увеличивает счетчик прокрутов для пользователя в конкретном чате"""
        try:
            today = date.today()
            limit = RouletteLimitRepository.get_or_create_limit(db, user_id, chat_id, today)
            limit.spin_count += 1
            db.commit()
            return True
        except Exception as e:
            print(f"❌ Ошибка увеличения счетчика прокрутов: {e}")
            db.rollback()
            return False

    @staticmethod
    def get_today_spin_count(db: Session, user_id: int, chat_id: int) -> int:
        """Возвращает количество прокрутов пользователя за сегодня в конкретном чате"""
        today = date.today()
        limit = db.query(models.RouletteLimit).filter(
            models.RouletteLimit.user_id == user_id,
            models.RouletteLimit.chat_id == chat_id,  # ДОБАВЬТЕ ЭТУ СТРОКУ
            models.RouletteLimit.date == today
        ).first()

        return limit.spin_count if limit else 0

    @staticmethod
    def cleanup_old_limits(db: Session, days_old: int = 7):
        """Очищает старые записи лимитов"""
        try:
            cutoff_date = date.today() - timedelta(days=days_old)
            deleted_count = db.query(models.RouletteLimit).filter(
                models.RouletteLimit.date < cutoff_date
            ).delete()
            db.commit()
            return deleted_count
        except Exception as e:
            print(f"❌ Ошибка очистки старых лимитов: {e}")
            db.rollback()
            return 0

    @staticmethod
    def get_user_chat_limit_stats(db: Session, user_id: int, chat_id: int) -> dict:
        """Возвращает статистику лимитов пользователя в конкретном чате"""
        today = date.today()

        # Сегодняшняя запись
        today_record = db.query(models.RouletteLimit).filter(
            models.RouletteLimit.user_id == user_id,
            models.RouletteLimit.chat_id == chat_id,
            models.RouletteLimit.date == today
        ).first()

        # Общая статистика по этому чату
        chat_stats = db.query(
            func.count(models.RouletteLimit.id).label('total_days'),
            func.sum(models.RouletteLimit.spin_count).label('total_spins')
        ).filter(
            models.RouletteLimit.user_id == user_id,
            models.RouletteLimit.chat_id == chat_id
        ).first()

        return {
            'today_spins': today_record.spin_count if today_record else 0,
            'total_days_in_chat': chat_stats.total_days or 0,
            'total_spins_in_chat': chat_stats.total_spins or 0
        }

    @staticmethod
    def get_user_purchases_by_chat(db: Session, user_id: int) -> List[models.UserPurchase]:
        """Получает покупки пользователя (для проверки снятия лимита)"""
        return db.query(models.UserPurchase).filter(
            models.UserPurchase.user_id == user_id
        ).all()


class ChatStatsRepository:
    @staticmethod
    def add_chat(db: Session, chat_id: int, chat_title: str = None, chat_type: str = None) -> models.Chat:
        """Добавляет чат в базу данных"""
        try:
            chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
            if not chat:
                chat = models.Chat(
                    chat_id=chat_id,
                    title=chat_title,
                    chat_type=chat_type,
                    is_active=True
                )
                db.add(chat)
                db.commit()
                db.refresh(chat)
                print(f"✅ Добавлен чат: {chat_id} ({chat_title})")
            return chat
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка добавления чата: {e}")
            return None

    @staticmethod
    def update_chat_title(db: Session, chat_id: int, new_title: str) -> bool:
        """Обновляет название чата"""
        try:
            chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
            if chat:
                chat.title = new_title
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка обновления названия чата: {e}")
            return False

    @staticmethod
    def get_all_chats(db: Session) -> List[int]:
        """Получает все уникальные chat_id из таблицы UserChat"""
        try:
            # Получаем все уникальные chat_id из UserChat
            chat_ids = db.query(models.UserChat.chat_id).distinct().all()
            return [chat_id[0] for chat_id in chat_ids]
        except Exception as e:
            print(f"❌ Ошибка получения чатов: {e}")
            return []

    @staticmethod
    def get_chat_stats(db: Session, chat_id: int) -> dict:
        """Получает статистику чата"""
        try:
            # Базовая информация о чате
            chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
            if not chat:
                return {}

            # Количество участников
            members_count = db.query(models.UserChat).filter(
                models.UserChat.chat_id == chat_id
            ).count()

            # Активность за последнюю неделю
            week_ago = datetime.now() - timedelta(days=7)
            recent_activity = db.query(models.RouletteTransaction).filter(
                models.RouletteTransaction.chat_id == chat_id,
                models.RouletteTransaction.created_at >= week_ago
            ).count()

            # Топ пользователей по балансу в этом чате
            top_users = ChatRepository.get_top_rich_in_chat(db, chat_id, limit=5)

            return {
                'chat_id': chat_id,
                'title': chat.title,
                'type': chat.chat_type,
                'members_count': members_count,
                'recent_activity': recent_activity,
                'top_users': top_users,
                'created_at': chat.created_at
            }
        except Exception as e:
            print(f"❌ Ошибка получения статистики чата: {e}")
            return {}



from datetime import datetime
# database/crud.py (исправленный класс BotStopRepository)
class BotStopRepository:
    @staticmethod
    def create_block_record(db, user_id: int, blocked_user_id: int):
        """Создает запись о блокировке пользователя с защитой от дублей и сбоев последовательности"""
        try:
            # Проверяем, существует ли уже такая запись
            existing = db.query(models.BotStop).filter(
                models.BotStop.user_id == user_id,
                models.BotStop.blocked_user_id == blocked_user_id
            ).first()

            if existing:
                return existing

            record = models.BotStop(
                user_id=user_id,
                blocked_user_id=blocked_user_id,
                created_at=datetime.now()
            )
            db.add(record)
            db.commit() # Пытаемся сохранить
            return record

        except Exception as e:
            db.rollback()
            # Проверяем, не является ли это ошибкой уникальности или последовательности
            if "UniqueViolation" in str(e) or "duplicate key" in str(e):
                print(f"⚠️ Обнаружена проблема с последовательностью BotStop: {e}")
                # Попытка исправить последовательность
                BotStopRepository._fix_sequence(db)
                
                # Пробуем снова
                try:
                    record = models.BotStop(
                        user_id=user_id,
                        blocked_user_id=blocked_user_id,
                        created_at=datetime.now()
                    )
                    db.add(record)
                    db.commit()
                    print("✅ Запись успешно создана после исправления последовательности")
                    return record
                except Exception as e2:
                    print(f"❌ Не удалось создать запись даже после исправления: {e2}")
                    return None
            else:
                print(f"❌ Ошибка создания записи блокировки: {e}")
                return None

    @staticmethod
    def _fix_sequence(db):
        """Исправляет последовательность ID таблицы"""
        from sqlalchemy import text
        try:
            # Для PostgreSQL
            db.execute(text(
                "SELECT setval('bot_stop_users_id_seq', (SELECT COALESCE(MAX(id), 0) FROM bot_stop_users) + 1, false)"
            ))
            db.commit()
            print("✅ Последовательность bot_stop_users_id_seq исправлена")
        except Exception as e:
            print(f"⚠️ Не удалось исправить последовательность (возможно не Postgres): {e}")

    @staticmethod
    def get_block_record(db, user_id: int, blocked_user_id: int):
        """Получает запись о блокировке"""
        return db.query(models.BotStop).filter(
            models.BotStop.user_id == user_id,
            models.BotStop.blocked_user_id == blocked_user_id
        ).first()

    @staticmethod
    def delete_block_record(db, user_id: int, blocked_user_id: int):
        """Удаляет запись о блокировке"""
        try:
            # Сначала проверим, существует ли запись
            existing = db.query(models.BotStop).filter(
                models.BotStop.user_id == user_id,
                models.BotStop.blocked_user_id == blocked_user_id
            ).first()

            if existing:
                logger.info(f"🔍 BEFORE DELETE: Найдена запись {user_id} -> {blocked_user_id}")

                # Удаляем запись
                db.query(models.BotStop).filter(
                    models.BotStop.user_id == user_id,
                    models.BotStop.blocked_user_id == blocked_user_id
                ).delete()

                # Проверяем что запись удалена
                after_delete = db.query(models.BotStop).filter(
                    models.BotStop.user_id == user_id,
                    models.BotStop.blocked_user_id == blocked_user_id
                ).first()

                if after_delete is None:
                    logger.info(f"✅ DELETE SUCCESS: Запись {user_id} -> {blocked_user_id} удалена")
                else:
                    logger.error(f"❌ DELETE FAILED: Запись {user_id} -> {blocked_user_id} все еще существует!")
            else:
                logger.warning(f"⚠️ DELETE: Запись {user_id} -> {blocked_user_id} не найдена")

        except Exception as e:
            logger.error(f"❌ DELETE ERROR: Ошибка удаления записи {user_id} -> {blocked_user_id}: {e}")
            raise

    @staticmethod
    def is_reply_blocked(db, current_user_id: int, replied_to_user_id: int) -> bool:
        """
        Проверяет, может ли current_user_id отвечать на сообщения replied_to_user_id
        Возвращает True если ответ ЗАБЛОКИРОВАН

        Правильная логика:
        - user1 использует "бот стоп" на user2 → создается запись (user1, user2)
        - Это означает: "user1 заблокировал user2"
        - Когда user2 отвечает на user1 → проверяем: "user1 заблокировал user2?" = ДА → удаляем
        """
        # Ищем запись где:
        # user_id = replied_to_user_id (тот, на чье сообщение отвечают)
        # blocked_user_id = current_user_id (тот, кто отвечает)
        # Это означает: "replied_to_user_id заблокировал current_user_id"
        record = db.query(models.BotStop).filter(
            models.BotStop.user_id == replied_to_user_id,
            models.BotStop.blocked_user_id == current_user_id
        ).first()

        is_blocked = record is not None
        logger.info(f"🔍 BLOCK CHECK: {replied_to_user_id} заблокировал {current_user_id} = {is_blocked}")
        return is_blocked


# database/crud.py (УЛУЧШЕННЫЙ класс BotSearchRepository)
class BotSearchRepository:
    # database/crud.py - в методе add_user_chat
    @staticmethod
    def add_user_chat(db, user_id: int, chat_id: int, chat_title: str):
        """Добавляет или обновляет чат пользователя в базе данных"""
        from database.models import UserChatSearch
        try:
            # Проверяем, существует ли уже такая запись
            existing = db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id,
                UserChatSearch.chat_id == chat_id
            ).first()

            if existing:
                # Обновляем существующую запись
                existing.chat_title = chat_title
                # Если нет поля last_activity, просто обновляем created_at
                # или используем другой подход:
                try:
                    existing.last_activity = datetime.now()
                except AttributeError:
                    # Если поле не существует, просто пропускаем
                    pass
                print(f"🔄 Обновлен чат пользователя {user_id}: {chat_title}")
            else:
                # Создаем новую запись без last_activity
                record = UserChatSearch(
                    user_id=user_id,
                    chat_id=chat_id,
                    chat_title=chat_title,
                    # Не добавляем last_activity, если его нет в модели
                )
                db.add(record)
                print(f"✅ Добавлен новый чат пользователя {user_id}: {chat_title}")

            db.commit()
            return True
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка добавления чата пользователя: {e}")
            return False

    @staticmethod
    def add_user_nick(db, user_id: int, nick: str):
        """Добавляет ник пользователя в базу данных"""
        from database.models import UserNickSearch
        try:
            # Очищаем ник от лишних пробелов
            nick = ' '.join(nick.split()).strip()

            if not nick or len(nick) > 255:
                return False

            # Проверяем, существует ли уже такая запись
            existing = db.query(UserNickSearch).filter(
                UserNickSearch.user_id == user_id,
                UserNickSearch.nick == nick
            ).first()

            if not existing:
                record = UserNickSearch(
                    user_id=user_id,
                    nick=nick
                )
                db.add(record)
                db.commit()
                print(f"✅ Добавлен новый ник пользователя {user_id}: {nick}")
                return True
            return False
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка добавления ника пользователя: {e}")
            return False

    @staticmethod
    def get_user_chats(db, user_id: int) -> List[Tuple[int, str]]:
        """Получает список чатов, где находится пользователь"""
        try:
            from database.models import UserChatSearch

            chats = db.query(UserChatSearch.chat_id, UserChatSearch.chat_title) \
                .filter(UserChatSearch.user_id == user_id) \
                .order_by(UserChatSearch.created_at.desc()) \
                .all()
            return [(chat_id, chat_title) for chat_id, chat_title in chats]
        except Exception as e:
            logger.error(f"Error getting user chats for {user_id}: {e}")
            return []

    @staticmethod
    def get_user_chats_with_activity(db, user_id: int, limit: int = 50):
        """Получает чаты пользователя с информацией об активности"""
        from database.models import UserChatSearch
        try:
            chats = db.query(
                UserChatSearch.chat_title,
                UserChatSearch.chat_id,
                UserChatSearch.last_activity
            ).filter(
                UserChatSearch.user_id == user_id
            ).order_by(
                UserChatSearch.last_activity.desc().nullslast(),
                UserChatSearch.created_at.desc()
            ).limit(limit).all()
            return chats
        except Exception as e:
            print(f"❌ Ошибка получения чатов с активностью: {e}")
            return []

    @staticmethod
    def get_user_nicks(db, user_id: int, limit: int = 20):
        """Получает список ников пользователя"""
        from database.models import UserNickSearch
        try:
            nicks = db.query(UserNickSearch.nick).filter(
                UserNickSearch.user_id == user_id
            ).order_by(UserNickSearch.created_at.desc()).limit(limit).all()
            return [nick for (nick,) in nicks]
        except Exception as e:
            print(f"❌ Ошибка получения ников пользователя: {e}")
            return []

    @staticmethod
    def get_user_nicks_with_dates(db, user_id: int, limit: int = 20):
        """Получает ники пользователя с датами"""
        from database.models import UserNickSearch
        try:
            nicks = db.query(
                UserNickSearch.nick,
                UserNickSearch.created_at
            ).filter(
                UserNickSearch.user_id == user_id
            ).order_by(
                UserNickSearch.created_at.desc()
            ).limit(limit).all()
            return nicks
        except Exception as e:
            print(f"❌ Ошибка получения ников с датами: {e}")
            return []

    @staticmethod
    def get_first_seen_date(db, user_id: int):
        """Получает дату первого появления пользователя"""
        from database.models import UserChatSearch
        try:
            result = db.query(
                func.min(UserChatSearch.created_at)
            ).filter(
                UserChatSearch.user_id == user_id
            ).scalar()
            return result
        except Exception as e:
            print(f"❌ Ошибка получения даты первого появления: {e}")
            return None

    @staticmethod
    def get_last_seen_date(db, user_id: int):
        """Получает дату последней активности"""
        from database.models import UserChatSearch
        try:
            # Сначала пытаемся получить по last_activity
            result = db.query(
                func.max(UserChatSearch.last_activity)
            ).filter(
                UserChatSearch.user_id == user_id
            ).scalar()

            if result:
                return result

            # Если нет last_activity, используем created_at
            return db.query(
                func.max(UserChatSearch.created_at)
            ).filter(
                UserChatSearch.user_id == user_id
            ).scalar()
        except Exception as e:
            print(f"❌ Ошибка получения даты последней активности: {e}")
            return None

    @staticmethod
    def get_user_command_count(db, user_id: int):
        """Считает общее количество активностей пользователя"""
        from database.models import UserChatSearch
        try:
            return db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id
            ).count()
        except Exception as e:
            print(f"❌ Ошибка получения количества активностей: {e}")
            return 0

    @staticmethod
    def cleanup_old_data(db, days_old: int = 30):
        """Очищает старые данные поиска"""
        from database.models import UserChatSearch, UserNickSearch
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)

            # Удаляем старые записи чатов
            deleted_chats = db.query(UserChatSearch).filter(
                UserChatSearch.last_activity < cutoff_date
            ).delete()

            # Удаляем старые записи ников
            deleted_nicks = db.query(UserNickSearch).filter(
                UserNickSearch.created_at < cutoff_date
            ).delete()

            db.commit()
            print(f"✅ Очищено данных поиска: {deleted_chats} чатов, {deleted_nicks} ников")
            return {'chats': deleted_chats, 'nicks': deleted_nicks}
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка очистки старых данных: {e}")
            return {'chats': 0, 'nicks': 0}

    @staticmethod
    def get_user_search_stats(db, user_id: int):
        """Получает статистику поиска по пользователю"""
        from database.models import UserChatSearch, UserNickSearch
        try:
            # Количество чатов
            chats_count = db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id
            ).count()

            # Количество ников
            nicks_count = db.query(UserNickSearch).filter(
                UserNickSearch.user_id == user_id
            ).count()

            # Дата первого появления
            first_seen = BotSearchRepository.get_first_seen_date(db, user_id)

            # Дата последней активности
            last_seen = BotSearchRepository.get_last_seen_date(db, user_id)

            return {
                'chats_count': chats_count,
                'nicks_count': nicks_count,
                'first_seen': first_seen,
                'last_seen': last_seen,
                'total_activities': BotSearchRepository.get_user_command_count(db, user_id)
            }
        except Exception as e:
            print(f"❌ Ошибка получения статистики поиска: {e}")
            return {
                'chats_count': 0,
                'nicks_count': 0,
                'first_seen': None,
                'last_seen': None,
                'total_activities': 0
            }

    @staticmethod
    def log_user_activity(db, user_id: int, chat_id: int, chat_title: str, nick: str):
        """Комплексное логирование активности пользователя"""
        try:
            # Логируем чат
            chat_success = BotSearchRepository.add_user_chat(db, user_id, chat_id, chat_title)

            # Логируем ник
            nick_success = BotSearchRepository.add_user_nick(db, user_id, nick)

            return {
                'chat_logged': chat_success,
                'nick_logged': nick_success,
                'timestamp': datetime.now()
            }
        except Exception as e:
            print(f"❌ Ошибка логирования активности: {e}")
            return {
                'chat_logged': False,
                'nick_logged': False,
                'timestamp': datetime.now()
            }

    @staticmethod
    def search_users_by_nick(db, search_term: str, limit: int = 20):
        """Ищет пользователей по нику"""
        from database.models import UserNickSearch
        try:
            search_pattern = f"%{search_term}%"
            results = db.query(
                UserNickSearch.user_id,
                UserNickSearch.nick
            ).filter(
                UserNickSearch.nick.ilike(search_pattern)
            ).distinct().limit(limit).all()

            return [(user_id, nick) for user_id, nick in results]
        except Exception as e:
            print(f"❌ Ошибка поиска пользователей по нику: {e}")
            return []

    @staticmethod
    def get_chat_users(db, chat_id: int, limit: int = 50):
        """Получает пользователей из конкретного чата"""
        from database.models import UserChatSearch
        try:
            users = db.query(
                UserChatSearch.user_id
            ).filter(
                UserChatSearch.chat_id == chat_id
            ).distinct().limit(limit).all()

            return [user_id for (user_id,) in users]
        except Exception as e:
            print(f"❌ Ошибка получения пользователей чата: {e}")
            return []


class ThiefRepository:
    @staticmethod
    def get_user_arrest(db, user_id: int):
        """Получает информацию об аресте пользователя"""
        from database.models import ThiefArrest
        return db.query(ThiefArrest).filter(
            ThiefArrest.user_id == user_id,
            ThiefArrest.release_time > datetime.now()
        ).first()

    @staticmethod
    def arrest_user(db, user_id: int, release_time: datetime):
        """Арестовывает пользователя"""
        from database.models import ThiefArrest
        # Удаляем старые аресты
        db.query(ThiefArrest).filter(ThiefArrest.user_id == user_id).delete()

        # Создаем новый арест
        arrest = ThiefArrest(
            user_id=user_id,
            release_time=release_time
        )
        db.add(arrest)

    @staticmethod
    def get_last_steal_time(db, user_id: int):
        """Получает время последней кражи пользователя"""
        from database.models import StealAttempt
        last_attempt = db.query(StealAttempt).filter(
            StealAttempt.thief_id == user_id
        ).order_by(StealAttempt.attempt_time.desc()).first()

        return last_attempt.attempt_time if last_attempt else None

    @staticmethod
    def get_user_balance(db, user_id: int) -> int:
        """Получает баланс пользователя"""
        from database.models import TelegramUser
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == user_id).first()
        return int(user.coins) if user and user.coins else 0

    @staticmethod
    def update_user_balance(db, user_id: int, new_balance: int):
        """Обновляет баланс пользователя"""
        from database.models import TelegramUser
        user = db.query(TelegramUser).filter(TelegramUser.telegram_id == user_id).first()
        if user:
            user.coins = new_balance

    @staticmethod
    def record_steal_attempt(db, thief_id: int, victim_id: int, successful: bool, amount: int):
        """Записывает попытку кражи (ПОЛНОСТЬЮ ПЕРЕПИСАННЫЙ МЕТОД)"""
        from sqlalchemy import text

        try:
            # Способ 1: Прямой SQL запрос с ручным вычислением следующего ID
            max_id_result = db.execute(text("SELECT COALESCE(MAX(id), 0) FROM steal_attempts")).fetchone()
            next_id = max_id_result[0] + 1 if max_id_result else 1

            db.execute(
                text("""
                     INSERT INTO steal_attempts
                         (id, thief_id, victim_id, successful, amount, attempt_time)
                     VALUES (:id, :thief_id, :victim_id, :successful, :amount, :attempt_time)
                     """),
                {
                    'id': next_id,
                    'thief_id': thief_id,
                    'victim_id': victim_id,
                    'successful': successful,
                    'amount': amount,
                    'attempt_time': datetime.now()
                }
            )
            print(f"✅ Запись кражи добавлена с ID: {next_id}")
            return True

        except Exception as e:
            print(f"❌ Критическая ошибка записи попытки кражи: {e}")
            # В случае ошибки просто пропускаем запись в историю
            return False

    @staticmethod
    def _fix_sequence(db):
        """Исправляет последовательность для таблицы steal_attempts"""
        from sqlalchemy import text

        try:
            # Для PostgreSQL - исправляем последовательность
            db.execute(text(
                "SELECT setval('steal_attempts_id_seq', (SELECT COALESCE(MAX(id), 0) FROM steal_attempts) + 1, false)"
            ))
            print("✅ Последовательность steal_attempts_id_seq исправлена")
        except Exception as e:
            print(f"⚠️ Не удалось исправить последовательность: {e}")

    @staticmethod
    def get_user_thief_stats(db, user_id: int) -> dict:
        """Получает статистику краж пользователя"""
        from database.models import StealAttempt, ThiefArrest

        # Статистика краж
        successful_steals = db.query(StealAttempt).filter(
            StealAttempt.thief_id == user_id,
            StealAttempt.successful == True
        ).count()

        failed_steals = db.query(StealAttempt).filter(
            StealAttempt.thief_id == user_id,
            StealAttempt.successful == False
        ).count()

        total_stolen = db.query(func.sum(StealAttempt.amount)).filter(
            StealAttempt.thief_id == user_id,
            StealAttempt.successful == True
        ).scalar() or 0

        total_arrests = db.query(ThiefArrest).filter(
            ThiefArrest.user_id == user_id
        ).count()

        last_steal_time = db.query(StealAttempt.attempt_time).filter(
            StealAttempt.thief_id == user_id
        ).order_by(StealAttempt.attempt_time.desc()).first()

        return {
            'successful_steals': successful_steals,
            'failed_steals': failed_steals,
            'total_stolen': int(total_stolen),
            'total_arrests': total_arrests,
            'last_steal_time': last_steal_time[0] if last_steal_time else None
        }

    @staticmethod
    def get_last_steal_time_by_victim(db, victim_id: int):
        """Получает время последней кражи у жертвы"""
        from database.models import StealAttempt
        last_attempt = db.query(StealAttempt).filter(
            StealAttempt.victim_id == victim_id
        ).order_by(StealAttempt.attempt_time.desc()).first()

        return last_attempt.attempt_time if last_attempt else None


# database/crud.py
class PoliceRepository:


    @staticmethod
    def get_user_arrest(db, user_id: int):
        """Получает информацию об аресте пользователя"""
        from database.models import UserArrest
        return db.query(UserArrest).filter(
            UserArrest.user_id == user_id,
            UserArrest.release_time > datetime.now()
        ).first()

    @staticmethod
    def unarrest_user(db, user_id: int) -> bool:
        """Снимает арест с пользователя"""
        from database.models import UserArrest
        deleted_count = db.query(UserArrest).filter(UserArrest.user_id == user_id).delete()
        return deleted_count > 0

    @staticmethod
    def get_all_active_arrests(db):
        """Получает все активные аресты"""
        from database.models import UserArrest
        return db.query(UserArrest).filter(
            UserArrest.release_time > datetime.now()
        ).all()

    @staticmethod
    def get_arrests_by_police(db, police_id: int):
        """Получает все аресты, выполненные конкретным полицейским"""
        from database.models import UserArrest
        return db.query(UserArrest).filter(
            UserArrest.arrested_by == police_id
        ).all()


    @staticmethod
    def get_last_arrest_by_police(db, police_id: int):
        """Получает последний арест, выполненный полицейским"""
        from database.models import UserArrest
        try:
            last_arrest = db.query(UserArrest)\
                .filter(UserArrest.arrested_by == police_id)\
                .order_by(UserArrest.release_time.desc())\
                .first()
            return last_arrest
        except Exception as e:
            print(f"❌ Ошибка получения последнего ареста полицейского {police_id}: {e}")
            return None


    @staticmethod
    def cleanup_expired_arrests(db) -> int:
        """Очищает истекшие аресты и возвращает количество удаленных"""
        from database.models import UserArrest
        deleted_count = db.query(UserArrest).filter(
            UserArrest.release_time <= datetime.now()
        ).delete()
        return deleted_count

    @staticmethod
    def arrest_user(db, user_id: int, arrested_by: int, release_time: datetime):
        """Арестовывает пользователя с указанием кто арестовал"""
        from database.models import UserArrest

        # Сначала удаляем старую запись если есть
        db.query(UserArrest).filter(UserArrest.user_id == user_id).delete()

        # Создаем новый арест
        arrest = UserArrest(
            user_id=user_id,
            arrested_by=arrested_by,
            release_time=release_time
        )
        db.add(arrest)

# database/crud.py (добавьте в конец файла)
class DonateRepository:
    @staticmethod
    def add_donate_purchase(db, user_id: int, item_id: int, item_name: str, duration_days: int = None):
        """Добавляет покупку донат-привилегии"""
        from database.models import DonatePurchase

        expires_at = None
        if duration_days:
            expires_at = datetime.now() + timedelta(days=duration_days)

        # Удаляем старую запись если есть
        db.query(DonatePurchase).filter(
            DonatePurchase.user_id == user_id,
            DonatePurchase.item_id == item_id
        ).delete()

        purchase = DonatePurchase(
            user_id=user_id,
            item_id=item_id,
            item_name=item_name,
            expires_at=expires_at
        )
        db.add(purchase)
        return purchase

    @staticmethod
    def has_active_purchase(db, user_id: int, item_id: int) -> bool:
        """Проверяет, есть ли у пользователя активная покупка"""
        from database.models import DonatePurchase

        purchase = db.query(DonatePurchase).filter(
            DonatePurchase.user_id == user_id,
            DonatePurchase.item_id == item_id
        ).first()

        return purchase is not None and purchase.is_active()

    @staticmethod
    def get_user_active_purchases(db, user_id: int):
        """Получает активные покупки пользователя с учетом срока действия"""
        from database.models import UserPurchase
        from datetime import datetime

        try:
            current_time = datetime.now()

            # Получаем все покупки пользователя
            purchases = db.query(UserPurchase).filter(
                UserPurchase.user_id == user_id
            ).all()

            active_purchases = []
            for purchase in purchases:
                # Проверяем активность
                if hasattr(purchase, 'is_active') and not purchase.is_active:
                    continue

                # Проверяем срок действия
                if purchase.expires_at and purchase.expires_at <= current_time:
                    # Если привилегия истекла, помечаем как неактивную
                    if hasattr(purchase, 'is_active'):
                        purchase.is_active = False
                        db.commit()
                    continue

                active_purchases.append(purchase)

            return active_purchases

        except Exception as e:
            print(f"❌ Ошибка получения активных покупок: {e}")
            return []



    @staticmethod
    def cleanup_expired_purchases(db):
        """Очищает истекшие покупки"""
        from database.models import DonatePurchase

        deleted_count = db.query(DonatePurchase).filter(
            DonatePurchase.expires_at <= datetime.now()
        ).delete()
        return deleted_count

    @staticmethod
    def can_user_steal(db, user_id: int) -> bool:
        """Проверяет, может ли пользователь красть (вор в законе)"""
        return DonateRepository.has_active_purchase(db, user_id, 1)  # item_id = 1

    @staticmethod
    def can_user_arrest(db, user_id: int) -> bool:
        """Проверяет, может ли пользователь арестовывать (полицейский)"""
        return DonateRepository.has_active_purchase(db, user_id, 2)  # item_id = 2

    @staticmethod
    def has_active_donate_purchase(db, user_id: int, item_id: int) -> bool:
        """Проверяет, есть ли у пользователя активная донат-покупка"""
        try:
            purchase = db.query(models.DonatePurchase).filter(
                models.DonatePurchase.user_id == user_id,
                models.DonatePurchase.item_id == item_id
            ).first()

            if not purchase:
                return False

            return purchase.is_active()

        except Exception as e:
            print(f"❌ Ошибка проверки активной донат-покупки: {e}")
            return False

    @staticmethod
    def get_active_donate_purchases(db, user_id: int) -> List[int]:
        """Получает список ID активных донат-покупок пользователя"""
        try:
            purchases = db.query(models.DonatePurchase).filter(
                models.DonatePurchase.user_id == user_id
            ).all()

            return [p.item_id for p in purchases if p.is_active()]

        except Exception as e:
            print(f"❌ Ошибка получения активных донат-покупок: {e}")
            return []


class TelegramUserRepository:
    @staticmethod
    def get_user_by_id(db, user_id: int):
        """Получает пользователя по ID"""
        return db.execute(
            "SELECT * FROM telegram_users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    @staticmethod
    def create_user(db, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Создает нового пользователя"""
        db.execute(
            "INSERT INTO telegram_users (user_id, username, first_name, last_name, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (user_id, username, first_name, last_name)
        )

class ModerationLogRepository:
    @staticmethod
    def add_log(
        db: Session,
        action: ModerationAction,
        chat_id: int,
        user_id: int,
        admin_id: int,
        reason: str = "",
        duration_minutes: Optional[int] = None
    ):
        log = ModerationLog(
            action=action,
            chat_id=chat_id,
            user_id=user_id,
            admin_id=admin_id,
            reason=reason,
            duration_minutes=duration_minutes
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log



class GroupInviteRepository:
    """Репозиторий для работы с приглашениями в группы"""

    @staticmethod
    def add_invite(db: Session, inviter_id: int, invited_id: int, chat_id: int):
        """Добавляет запись о приглашении пользователя в группу"""
        try:
            # Проверяем, не был ли уже приглашен этот пользователь в эту группу
            existing = db.query(models.GroupInvite).filter(
                models.GroupInvite.invited_id == invited_id,
                models.GroupInvite.chat_id == chat_id
            ).first()

            if existing:
                return existing

            invite = models.GroupInvite(
                inviter_id=inviter_id,
                invited_id=invited_id,
                chat_id=chat_id
            )
            db.add(invite)
            db.commit()
            db.refresh(invite)
            print(f"✅ Запись о приглашении добавлена: {inviter_id} -> {invited_id} в чат {chat_id}")
            return invite

        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка добавления приглашения: {e}")
            return None

    @staticmethod
    def get_invites_count(db: Session, inviter_id: int, chat_id: int = None) -> int:
        """Получает количество пользователей, приглашенных указанным пользователем"""
        try:
            query = db.query(models.GroupInvite).filter(
                models.GroupInvite.inviter_id == inviter_id
            )

            if chat_id:
                query = query.filter(models.GroupInvite.chat_id == chat_id)

            return query.count()

        except Exception as e:
            print(f"❌ Ошибка получения количества приглашений: {e}")
            return 0

    @staticmethod
    def get_invited_users(db: Session, inviter_id: int, chat_id: int = None, limit: int = 50):
        """Получает список приглашенных пользователей"""
        try:
            query = db.query(models.GroupInvite).filter(
                models.GroupInvite.inviter_id == inviter_id
            )

            if chat_id:
                query = query.filter(models.GroupInvite.chat_id == chat_id)

            return query.order_by(models.GroupInvite.invited_at.desc()).limit(limit).all()

        except Exception as e:
            print(f"❌ Ошибка получения списка приглашенных: {e}")
            return []

    @staticmethod
    def get_inviter_for_user(db: Session, invited_id: int, chat_id: int):
        """Получает пользователя, который пригласил указанного пользователя в группу"""
        try:
            invite = db.query(models.GroupInvite).filter(
                models.GroupInvite.invited_id == invited_id,
                models.GroupInvite.chat_id == chat_id
            ).first()

            return invite.inviter_id if invite else None

        except Exception as e:
            print(f"❌ Ошибка получения пригласившего: {e}")
            return None

            db.commit()
            return deleted_count
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка очистки старых приглашений: {e}")
            return 0

    @staticmethod
    def reset_invites(db: Session, inviter_id: int, chat_id: int):
        """Сбрасывает счетчик приглашений пользователя в конкретном чате"""
        try:
            deleted_count = db.query(models.GroupInvite).filter(
                models.GroupInvite.inviter_id == inviter_id,
                models.GroupInvite.chat_id == chat_id
            ).delete()
            db.commit()
            print(f"✅ Сброшено {deleted_count} приглашений пользователя {inviter_id} в чате {chat_id}")
            return deleted_count
        except Exception as e:
            db.rollback()
            print(f"❌ Ошибка сброса приглашений: {e}")
            return -1