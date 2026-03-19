# handlers/donate/bonus.py

import logging
import time
from typing import Dict, Any, Tuple, List
from contextlib import contextmanager
from datetime import datetime, timedelta
from aiogram import types, Bot
from sqlalchemy import text
from .config import BONUS_AMOUNT, BONUS_COOLDOWN_HOURS, THIEF_BONUS_AMOUNT, POLICE_BONUS_AMOUNT, \
    PRIVILEGE_BONUS_COOLDOWN_HOURS, CHANNEL_USERNAME, CHANNEL_LINK, SUBSCRIPTION_BONUS_AMOUNT, \
    SUBSCRIPTION_CHECK_COOLDOWN
from database import get_db
from database.crud import UserRepository, DonateRepository

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """Класс для управления подписками на каналах"""

    @staticmethod
    async def check_subscription(bot: Bot, user_id: int) -> bool:
        """Проверяет, подписан ли пользователь на канал"""
        try:
            # Убираем @ если он есть в начале
            channel = CHANNEL_USERNAME.lstrip('@')

            # Пробуем получить информацию о канале
            try:
                chat = await bot.get_chat(f"@{channel}")
                logger.info(f"✅ Получена информация о канале {channel}")
            except Exception as e:
                logger.error(f"❌ Не удалось получить информацию о канале {channel}: {e}")
                return False

            # Пробуем получить статус пользователя в канале
            try:
                chat_member = await bot.get_chat_member(
                    chat_id=chat.id,
                    user_id=user_id
                )

                # Статусы, которые считаются подпиской
                valid_statuses = ["member", "administrator", "creator"]
                is_subscribed = chat_member.status in valid_statuses

                logger.info(
                    f"🔍 Проверка подписки для {user_id} на {channel}: статус={chat_member.status}, результат={is_subscribed}")
                return is_subscribed

            except Exception as e:
                error_msg = str(e).lower()
                # Обрабатываем разные ошибки
                if "user not found" in error_msg:
                    logger.info(f"👤 Пользователь {user_id} не найден в канале {channel} (не подписан)")
                    return False
                elif "chat not found" in error_msg:
                    logger.error(f"❌ Канал {channel} не найден")
                    return False
                elif "member list is inaccessible" in error_msg:
                    # Если бот не админ, используем альтернативный метод
                    logger.warning(f"⚠️ Бот не имеет доступа к списку участников канала {channel}")
                    logger.warning(
                        f"⚠️ Рекомендуется добавить бота как администратора в канал с правом 'просматривать участников'")
                    return await SubscriptionManager._check_subscription_alternative(bot, user_id, channel)
                else:
                    logger.error(f"❌ Ошибка проверки статуса пользователя {user_id} в канале {channel}: {e}")
                    return False

        except Exception as e:
            logger.error(f"❌ Общая ошибка проверки подписки: {e}")
            return False

    @staticmethod
    async def _check_subscription_alternative(bot: Bot, user_id: int, channel: str) -> bool:
        """Альтернативный метод проверки подписки (если бот не админ)"""
        try:
            # Попробуем отправить сообщение в канал и посмотреть результат
            # Это не идеальный метод, но может помочь
            logger.info(f"🔄 Используем альтернативный метод проверки подписки для {user_id}")

            # Попробуем получить информацию о пользователе в контексте канала
            try:
                # Создаем временную ссылку
                chat = await bot.get_chat(f"@{channel}")

                # Пробуем получить чат участника через forward
                try:
                    # Пробуем проверить через отправку сообщения (невидимого)
                    # Но это может не работать, если бот не админ
                    chat_member = await bot.get_chat_member(chat.id, user_id)
                    valid_statuses = ["member", "administrator", "creator"]
                    return chat_member.status in valid_statuses
                except:
                    # Если не работает, предполагаем что пользователь не подписан
                    logger.warning(
                        f"⚠️ Не удалось проверить подписку для {user_id} - бот должен быть администратором в канале")
                    return False

            except Exception as e:
                logger.error(f"❌ Альтернативный метод проверки не сработал: {e}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка в альтернативном методе проверки: {e}")
            return False


class BonusManager:
    """Класс для управления бонусами с ручным начислением по кнопке"""

    def __init__(self):
        self._init_bonus_table()

    def _init_bonus_table(self):
        """Создает таблицу для бонусов если ее нет и добавляет недостающие колонки"""
        with self._db_session() as db:
            try:
                # Создаем таблицу если ее нет
                db.execute(text('''
                    CREATE TABLE IF NOT EXISTS user_bonuses
                    (
                        id SERIAL PRIMARY KEY,
                        telegram_id BIGINT UNIQUE NOT NULL,
                        last_bonus_time BIGINT DEFAULT 0,
                        bonus_count INTEGER DEFAULT 0,
                        last_thief_bonus_time BIGINT DEFAULT 0,
                        last_police_bonus_time BIGINT DEFAULT 0,
                        thief_bonus_count INTEGER DEFAULT 0,
                        police_bonus_count INTEGER DEFAULT 0,
                        last_subscription_check BIGINT DEFAULT 0,
                        subscription_bonus_claimed BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                '''))

                # Проверяем существование колонок и добавляем если их нет
                columns_to_check = [
                    ('last_subscription_check', 'BIGINT DEFAULT 0'),
                    ('subscription_bonus_claimed', 'BOOLEAN DEFAULT FALSE')
                ]

                for column_name, column_type in columns_to_check:
                    try:
                        db.execute(text(f'''
                            ALTER TABLE user_bonuses 
                            ADD COLUMN IF NOT EXISTS {column_name} {column_type}
                        '''))
                    except Exception as e:
                        logger.warning(f"Колонка {column_name} уже существует или ошибка: {e}")

                db.commit()
                logger.info("✅ Таблица user_bonuses создана/проверена")
            except Exception as e:
                logger.error(f"❌ Ошибка создания таблицы бонусов: {e}")
                db.rollback()

    @contextmanager
    def _db_session(self):
        """Контекстный менеджер для безопасной работы с БД"""
        session = None
        try:
            session = next(get_db())
            yield session
        except Exception as e:
            logger.error(f"Database connection error in BonusManager: {e}")
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()

    async def claim_daily_bonus(self, user_id: int) -> Dict[str, Any]:
        """Выдает ежедневный бонус по кнопке (СТАРАЯ ВЕРСИЯ БЕЗ ПРОВЕРКИ ПОДПИСКИ)"""
        with self._db_session() as db:
            try:
                current_time = int(time.time())

                # Проверяем, когда был последний бонус
                bonus_info = db.execute(
                    text("SELECT last_bonus_time FROM user_bonuses WHERE telegram_id = :user_id"),
                    {"user_id": user_id}
                ).fetchone()

                # ИСПРАВЛЕНИЕ: Безопасное получение last_bonus_time
                last_bonus_time = 0
                if bonus_info and bonus_info[0] is not None:
                    last_bonus_time = int(bonus_info[0])

                cooldown_seconds = BONUS_COOLDOWN_HOURS * 3600

                # ИСПРАВЛЕНИЕ: Безопасная проверка кулдауна
                time_since_last_bonus = current_time - last_bonus_time

                if time_since_last_bonus < cooldown_seconds:
                    remaining_seconds = cooldown_seconds - time_since_last_bonus
                    hours_left = remaining_seconds // 3600
                    minutes_left = (remaining_seconds % 3600) // 60
                    return {
                        "success": False,
                        "available": False,
                        "hours_left": int(hours_left),
                        "minutes_left": int(minutes_left),
                        "bonus_amount": 0
                    }

                # Получаем активные привилегии пользователя
                user_purchases = DonateRepository.get_user_active_purchases(db, user_id)
                purchased_ids = [p.item_id for p in user_purchases]
                has_thief = 1 in purchased_ids
                has_police = 2 in purchased_ids

                # Начисляем бонусы
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    return {
                        "success": False,
                        "error": "Пользователь не найден",
                        "bonus_amount": 0
                    }

                bonus_amount = 0
                bonuses_claimed = []

                # Базовый бонус для всех
                user.coins += BONUS_AMOUNT
                bonus_amount += BONUS_AMOUNT
                bonuses_claimed.append("daily")

                # Дополнительные бонусы за привилегии
                if has_thief:
                    user.coins += THIEF_BONUS_AMOUNT
                    bonus_amount += THIEF_BONUS_AMOUNT
                    bonuses_claimed.append("thief")

                if has_police:
                    user.coins += POLICE_BONUS_AMOUNT
                    bonus_amount += POLICE_BONUS_AMOUNT
                    bonuses_claimed.append("police")

                # Обновляем время последнего бонуса
                db.execute(
                    text("""
                         INSERT INTO user_bonuses (telegram_id, last_bonus_time, bonus_count)
                         VALUES (:user_id, :time, 1) ON CONFLICT (telegram_id)
                                    DO
                         UPDATE SET last_bonus_time = EXCLUDED.last_bonus_time,
                             bonus_count = user_bonuses.bonus_count + 1
                         """),
                    {"user_id": user_id, "time": current_time}
                )

                db.commit()

                logger.info(f"✅ Бонус выдан пользователю {user_id}: {bonus_amount} монет, типы: {bonuses_claimed}")

                return {
                    "success": True,
                    "available": True,
                    "bonus_amount": bonus_amount,
                    "bonuses_claimed": bonuses_claimed,
                    "has_thief": has_thief,
                    "has_police": has_police
                }

            except Exception as e:
                logger.error(f"❌ Ошибка выдачи бонуса: {e}")
                db.rollback()
                return {
                    "success": False,
                    "error": str(e),
                    "bonus_amount": 0
                }

    async def claim_daily_bonus_with_subscription(self, bot: Bot, user_id: int) -> Dict[str, Any]:
        """Выдает ежедневный бонус по кнопке (С ПРОВЕРКОЙ ПОДПИСКИ)"""
        # Сначала проверяем подписку
        is_subscribed = await SubscriptionManager.check_subscription(bot, user_id)
        if not is_subscribed:
            return {
                "success": False,
                "error": f"Вы не подписаны на канал {CHANNEL_USERNAME}. Подпишитесь чтобы получать ежедневные бонусы!",
                "available": False,
                "needs_subscription": True
            }

        # Если подписан, выдаем бонус
        return await self.claim_daily_bonus(user_id)

    async def check_daily_bonus(self, user_id: int) -> Dict[str, Any]:
        """Проверяет доступность ежедневного бонуса"""
        with self._db_session() as db:
            try:
                result = db.execute(
                    text("SELECT last_bonus_time FROM user_bonuses WHERE telegram_id = :user_id"),
                    {"user_id": user_id}
                ).fetchone()

                current_time = int(time.time())

                # Если записи нет или last_bonus_time None, бонус доступен
                if not result or result[0] is None:
                    return {"available": True, "hours_left": 0, "minutes_left": 0}

                last_bonus_time = result[0]

                # Добавляем проверку на None и преобразуем к int
                if last_bonus_time is None:
                    return {"available": True, "hours_left": 0, "minutes_left": 0}

                last_bonus_time = int(last_bonus_time)
                time_since_last_bonus = current_time - last_bonus_time
                cooldown_seconds = BONUS_COOLDOWN_HOURS * 3600

                if time_since_last_bonus >= cooldown_seconds:
                    return {"available": True, "hours_left": 0, "minutes_left": 0}
                else:
                    remaining_seconds = cooldown_seconds - time_since_last_bonus
                    hours_left = remaining_seconds // 3600
                    minutes_left = (remaining_seconds % 3600) // 60
                    return {
                        "available": False,
                        "hours_left": int(hours_left),
                        "minutes_left": int(minutes_left)
                    }
            except Exception as e:
                logger.error(f"❌ Ошибка проверки ежедневного бонуса: {e}")
                return {"available": True, "hours_left": 0, "minutes_left": 0}

    async def check_privilege_bonus(self, user_id: int) -> Dict[str, Any]:
        """Проверяет доступность бонусов за привилегии"""
        with self._db_session() as db:
            try:
                # Получаем активные привилегии пользователя
                user_purchases = DonateRepository.get_user_active_purchases(db, user_id)
                purchased_ids = [p.item_id for p in user_purchases]
                has_thief = 1 in purchased_ids
                has_police = 2 in purchased_ids

                # Используем ту же логику, что и для обычного бонуса
                bonus_info = await self.check_daily_bonus(user_id)

                return {
                    "available": bonus_info["available"],
                    "hours_left": bonus_info["hours_left"],
                    "minutes_left": bonus_info["minutes_left"],
                    "has_thief": has_thief,
                    "has_police": has_police
                }

            except Exception as e:
                logger.error(f"❌ Ошибка проверки бонусов за привилегии: {e}")
                return {
                    "available": False,
                    "hours_left": 0,
                    "minutes_left": 0,
                    "has_thief": False,
                    "has_police": False
                }

    async def claim_subscription_bonus(self, bot: Bot, user_id: int) -> Dict[str, Any]:
        """Выдает бонус за подписку на канал"""
        with self._db_session() as db:
            try:
                current_time = int(time.time())

                # Проверяем, не получал ли пользователь уже бонус
                bonus_info = db.execute(
                    text("""
                        SELECT subscription_bonus_claimed, last_subscription_check 
                        FROM user_bonuses 
                        WHERE telegram_id = :user_id
                    """),
                    {"user_id": user_id}
                ).fetchone()

                # Если уже получал бонус
                if bonus_info and bonus_info[0] is True:
                    return {
                        "success": False,
                        "error": "Вы уже получали бонус за подписку",
                        "available": False
                    }

                # Проверяем кулдаун проверки
                if bonus_info and bonus_info[1]:
                    last_check = int(bonus_info[1])
                    if current_time - last_check < SUBSCRIPTION_CHECK_COOLDOWN:
                        remaining = SUBSCRIPTION_CHECK_COOLDOWN - (current_time - last_check)

                        # Показываем секунды если меньше минуты, иначе минуты
                        if remaining < 60:
                            time_text = f"{remaining} секунд"
                        else:
                            minutes = remaining // 60
                            time_text = f"{minutes} минут"

                        return {
                            "success": False,
                            "error": f"Проверка подписки доступна раз в минуту. Попробуйте через {time_text}.",
                            "available": False
                        }

                # Проверяем подписку
                logger.info(f"🔍 Проверяем подписку пользователя {user_id} на канал {CHANNEL_USERNAME}")
                is_subscribed = await SubscriptionManager.check_subscription(bot, user_id)

                if not is_subscribed:
                    # Обновляем время последней проверки
                    db.execute(
                        text("""
                            INSERT INTO user_bonuses (telegram_id, last_subscription_check)
                            VALUES (:user_id, :time)
                            ON CONFLICT (telegram_id)
                            DO UPDATE SET last_subscription_check = EXCLUDED.last_subscription_check
                        """),
                        {"user_id": user_id, "time": current_time}
                    )
                    db.commit()

                    return {
                        "success": False,
                        "error": f"Вы не подписаны на канал {CHANNEL_USERNAME}",
                        "available": True,
                        "needs_subscription": True
                    }

                # Начисляем бонус
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    return {
                        "success": False,
                        "error": "Пользователь не найден",
                        "available": False
                    }

                user.coins += SUBSCRIPTION_BONUS_AMOUNT

                # Отмечаем бонус как выданный
                db.execute(
                    text("""
                        INSERT INTO user_bonuses 
                        (telegram_id, subscription_bonus_claimed, last_subscription_check)
                        VALUES (:user_id, TRUE, :time)
                        ON CONFLICT (telegram_id)
                        DO UPDATE SET 
                            subscription_bonus_claimed = EXCLUDED.subscription_bonus_claimed,
                            last_subscription_check = EXCLUDED.last_subscription_check
                    """),
                    {"user_id": user_id, "time": current_time}
                )

                db.commit()
                logger.info(f"✅ Бонус за подписку выдан пользователю {user_id}: {SUBSCRIPTION_BONUS_AMOUNT} монет")

                return {
                    "success": True,
                    "available": True,
                    "bonus_amount": SUBSCRIPTION_BONUS_AMOUNT,
                    "message": f"🎉 Вы получили {SUBSCRIPTION_BONUS_AMOUNT} монет за подписку на канал!"
                }

            except Exception as e:
                logger.error(f"❌ Ошибка выдачи бонуса за подписку: {e}", exc_info=True)
                db.rollback()
                return {
                    "success": False,
                    "error": str(e),
                    "available": False
                }

    async def check_subscription_status(self, bot: Bot, user_id: int) -> Dict[str, Any]:
        """Проверяет статус подписки и доступность бонуса"""
        with self._db_session() as db:
            try:
                # Проверяем, получал ли пользователь бонус
                bonus_info = db.execute(
                    text("SELECT subscription_bonus_claimed FROM user_bonuses WHERE telegram_id = :user_id"),
                    {"user_id": user_id}
                ).fetchone()

                bonus_claimed = False
                if bonus_info and bonus_info[0] is True:
                    bonus_claimed = True

                if bonus_claimed:
                    return {
                        "bonus_claimed": True,
                        "available": False,
                        "message": "Вы уже получали бонус за подписку",
                        "channel_link": CHANNEL_LINK,
                        "channel_username": CHANNEL_USERNAME,
                        "bonus_amount": SUBSCRIPTION_BONUS_AMOUNT
                    }

                # Проверяем подписку
                is_subscribed = await SubscriptionManager.check_subscription(bot, user_id)

                return {
                    "bonus_claimed": False,
                    "subscribed": is_subscribed,
                    "available": not is_subscribed,  # Доступно, если не подписан
                    "channel_link": CHANNEL_LINK,
                    "channel_username": CHANNEL_USERNAME,
                    "bonus_amount": SUBSCRIPTION_BONUS_AMOUNT
                }

            except Exception as e:
                logger.error(f"❌ Ошибка проверки статуса подписки: {e}", exc_info=True)
                return {
                    "bonus_claimed": False,
                    "subscribed": False,
                    "available": True,
                    "channel_link": CHANNEL_LINK,
                    "channel_username": CHANNEL_USERNAME,
                    "bonus_amount": SUBSCRIPTION_BONUS_AMOUNT,
                    "error": str(e)
                }

    async def debug_user_privileges(self, user_id: int):
        """Отладочная информация о привилегиях пользователя"""
        with self._db_session() as db:
            try:
                debug_info = {
                    'user_id': user_id,
                    'active_privileges': [],
                    'bonus_info': {}
                }

                # Получаем активные привилегии через DonateRepository
                active_purchases = DonateRepository.get_user_active_purchases(db, user_id)
                debug_info['active_privileges'] = [{
                    'item_id': p.item_id,
                    'item_name': p.item_name,
                    'expires_at': p.expires_at
                } for p in active_purchases]

                # Получаем информацию о бонусах
                bonus_info = db.execute(
                    text("""
                        SELECT last_bonus_time, subscription_bonus_claimed, last_subscription_check
                        FROM user_bonuses 
                        WHERE telegram_id = :user_id
                    """),
                    {"user_id": user_id}
                ).fetchone()

                if bonus_info:
                    debug_info['bonus_info'] = {
                        'last_bonus_time': bonus_info[0],
                        'subscription_bonus_claimed': bonus_info[1],
                        'last_subscription_check': bonus_info[2]
                    }

                return debug_info

            except Exception as e:
                logger.error(f"❌ Ошибка отладки привилегий: {e}", exc_info=True)
                return {'error': str(e)}