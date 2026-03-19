# handlers/mute_ban.py
import asyncio
import re
import time
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from random import choice

from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Command
from aiogram.utils.exceptions import BadRequest

from database import get_db
from database.crud import UserRepository, ModerationLogRepository
from database.models import ModerationAction

# Конфигурация
ADMIN_IDS = [6090751674, 1054684037]

# Файлы хранения
BOT_BAN_STORAGE_FILE = "active_bans.json"

logger = logging.getLogger(__name__)


class BotBanManager:
    """Менеджер для управления банами в боте"""

    def __init__(self, mute_ban_manager):
        self.mute_ban_manager = mute_ban_manager
        self.bot = None
        self.bot_bans = self._load_bot_bans()
        self.cleanup_task = None
        self.recently_unbanned = set()
        self.middleware = None

    def _load_bot_bans(self) -> Dict:
        """Загружает баны из файла"""
        try:
            if os.path.exists(BOT_BAN_STORAGE_FILE):
                with open(BOT_BAN_STORAGE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки банов: {e}")
        return {}

    def _save_bot_bans(self):
        """Сохраняет баны в файл"""
        try:
            with open(BOT_BAN_STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.bot_bans, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения банов: {e}")

    def is_user_bot_banned(self, user_id: int) -> bool:
        """Проверяет, забанен ли пользователь в боте"""
        try:
            user_id_str = str(user_id)

            # Проверка недавно разбаненных
            if user_id in self.recently_unbanned:
                return False

            if user_id_str in self.bot_bans:
                ban_data = self.bot_bans[user_id_str]
                expires_at = ban_data.get('expires_at')

                # Удаление истекших банов
                if expires_at and time.time() > expires_at:
                    del self.bot_bans[user_id_str]
                    self._save_bot_bans()
                    return False
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки бана: {e}")
            return False

    async def ban_user_in_bot(self, user_id: int, admin_id: int,
                              reason: str = "Не указана", seconds: int = None) -> bool:
        """Банит пользователя в боте"""
        try:
            # Проверяем, не является ли пользователь админом БОТА
            if await self.mute_ban_manager._is_bot_admin(user_id):
                logger.warning(f"Попытка бана админа бота: {user_id}")
                return False

            user_id_str = str(user_id)
            ban_data = {
                'user_id': user_id,
                'admin_id': admin_id,
                'reason': reason,
                'banned_at': time.time(),
                'banned_at_text': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            if seconds:
                seconds = min(seconds, 315360000)  # Макс 10 лет
                ban_data['expires_at'] = time.time() + seconds
                ban_data['expires_at_text'] = (datetime.now() + timedelta(seconds=seconds)).strftime(
                    "%Y-%m-%d %H:%M:%S")

            self.bot_bans[user_id_str] = ban_data
            self._save_bot_bans()

            # Удаляем из недавно разбаненных
            self.recently_unbanned.discard(user_id)

            logger.info(f"Пользователь {user_id} забанен в боте на {seconds}с, причина: {reason}")
            return True
        except Exception as e:
            logger.error(f"Ошибка бана в боте: {e}")
            return False

    async def unban_user_in_bot(self, user_id: int) -> bool:
        """Разбанивает пользователя в боте"""
        try:
            user_id_str = str(user_id)
            if user_id_str in self.bot_bans:
                del self.bot_bans[user_id_str]
                self._save_bot_bans()

                # Добавляем в недавно разбаненных
                self.recently_unbanned.add(user_id)

                # Уведомляем middleware о разбане
                if self.middleware:
                    self.middleware.add_recently_unbanned(user_id)

                logger.info(f"Пользователь {user_id} разбанен в боте")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка разбана в боте: {e}")
            return False

    def get_ban_info(self, user_id: int) -> Optional[Dict]:
        """Получает информацию о бане"""
        try:
            return self.bot_bans.get(str(user_id))
        except Exception:
            return None

    def add_recently_unbanned(self, user_id: int):
        """Добавляет пользователя в недавно разбаненных"""
        self.recently_unbanned.add(user_id)

    def set_middleware(self, middleware):
        """Устанавливает ссылку на middleware"""
        self.middleware = middleware

    def set_bot(self, bot):
        """Устанавливает бота"""
        self.bot = bot

    def start_cleanup_task(self):
        """Запускает задачу очистки истекших банов"""
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_expired_bans())

    async def stop_cleanup_task(self):
        """Останавливает задачу очистки"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_expired_bans(self):
        """Фоновая задача очистки истекших банов"""
        while True:
            try:
                current_time = time.time()
                expired = []

                for user_id_str, ban_data in list(self.bot_bans.items()):
                    expires_at = ban_data.get('expires_at')
                    if expires_at and current_time > expires_at:
                        expired.append(user_id_str)
                        user_id = int(user_id_str)
                        self.add_recently_unbanned(user_id)

                        # Уведомляем middleware об авторазбане
                        if self.middleware:
                            self.middleware.add_recently_unbanned(user_id)

                for user_id_str in expired:
                    del self.bot_bans[user_id_str]

                if expired:
                    self._save_bot_bans()

                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в задаче очистки: {e}")
                await asyncio.sleep(300)

    async def restore_bans_after_restart(self):
        """Восстанавливает баны после перезапуска"""
        current_time = time.time()
        expired = []

        for user_id_str, ban_data in list(self.bot_bans.items()):
            expires_at = ban_data.get('expires_at')
            if expires_at and current_time > expires_at:
                expired.append(user_id_str)

        for user_id_str in expired:
            del self.bot_bans[user_id_str]

        if expired:
            self._save_bot_bans()

        logger.info(f"Восстановлено {len(self.bot_bans)} активных банов, удалено {len(expired)} истекших")


# Текстовые ответы
class ResponseTexts:
    """Класс с текстовыми ответами для модерации"""

    # Сообщения для мута
    MUTE_SUCCESS = [
        "✅ Пользователь успешно отправлен в режим тишины на {time}.",
        "🔇 Тишина на {time}. Отличная возможность подумать.",
        "🤫 Пользователь получил {time} на размышления. Говорить нельзя.",
        "📵 Режим тишины активирован на {time}. Время для медитации."
    ]

    # Сообщения для размута
    UNMUTE_SUCCESS = [
        "🔊 Тишина дала тебе проход обратно.\nГовори, но помни — стены тоже слушают.",
        "🎤 Микрофон снова включен. Будь осторожен со словами.",
        "🗣️ Право голоса возвращено. Используй его с умом.",
        "🎵 Звук вернулся в чат. Продолжаем общение."
    ]

    # Сообщения для бана
    BAN_SUCCESS = [
        "🚫 Пользователь исключён из чата без права возврата.",
        "⛔ Дверь захлопнулась навсегда. Прощай.",
        "🔒 Доступ закрыт. Возврата нет.",
        "👋 Прощание навсегда. Путь назад отрезан."
    ]

    # Сообщения для разбана
    UNBAN_SUCCESS = [
        "🔓 Дверь снова открыта. Можешь вернуться.",
        "🌅 Запрет снят. Добро пожаловать обратно.",
        "✅ Пользователь может вернуться в чат.",
        "🚪 Возвращение разрешено. Входи."
    ]

    # Сообщения для кика
    KICK_SUCCESS = [
        "👢 Пользователь выгнан из чата. Может вернуться по приглашению.",
        "💨 Ветер перемен вынес пользователя из чата.",
        "🚶‍♂️ Временное исключение. Возврат возможен.",
        "🏃‍♂️ Быстрый выход. Дверь остаётся открытой."
    ]

    # Сообщения для бана в боте
    BOTBAN_SUCCESS = [
        "🤖 Пользователь заблокирован в боте на {time}.",
        "🚫 Бот больше не будет отвечать этому пользователю на {time}.",
        "⚡ Доступ к боту ограничен на {time}.",
        "🔐 Замок на боте установлен на {time}."
    ]

    # Сообщения для разбана в боте
    BOTUNBAN_SUCCESS = [
        "🤖 Блокировка в боте снята.",
        "✅ Пользователь снова может общаться с ботом.",
        "🔓 Доступ к боту восстановлен.",
        "🌐 Связь с ботом возобновлена."
    ]

    # Ошибки
    ERROR_NO_RIGHTS = "❌ У вас нет прав администратора!"
    ERROR_BOT_NO_RIGHTS = "❌ У бота недостаточно прав для модерации!"
    ERROR_NO_REPLY = "❌ Ответьте на сообщение пользователя!"
    ERROR_ADMIN_TARGET = "❌ Нельзя применять модерацию к администраторам!"
    ERROR_ALREADY_MUTED = "ℹ️ Пользователь уже в режиме тишины."
    ERROR_NOT_MUTED = "ℹ️ Пользователь не ограничен в общении."
    ERROR_NOT_BANNED = "ℹ️ Пользователь не забанен."
    ERROR_GENERAL = "❌ Не удалось выполнить действие."
    ERROR_INVALID_TIME = "❌ Неверно указано время."
    ERROR_BOT_ADMIN_ONLY = "❌ Эта команда доступна только администраторам бота!"
    ERROR_CANT_BAN_BOT_ADMIN = "❌ Нельзя забанить администратора бота!"

    @classmethod
    def get_mute_success(cls, time_text: str) -> str:
        """Возвращает случайное сообщение об успешном муте"""
        return choice(cls.MUTE_SUCCESS).format(time=time_text)

    @classmethod
    def get_unmute_success(cls) -> str:
        """Возвращает случайное сообщение об успешном размуте"""
        return choice(cls.UNMUTE_SUCCESS)

    @classmethod
    def get_ban_success(cls) -> str:
        """Возвращает случайное сообщение об успешном бане"""
        return choice(cls.BAN_SUCCESS)

    @classmethod
    def get_unban_success(cls) -> str:
        """Возвращает случайное сообщение об успешном разбане"""
        return choice(cls.UNBAN_SUCCESS)

    @classmethod
    def get_kick_success(cls) -> str:
        """Возвращает случайное сообщение об успешном кике"""
        return choice(cls.KICK_SUCCESS)

    @classmethod
    def get_botban_success(cls, time_text: str = "всегда") -> str:
        """Возвращает случайное сообщение об успешном бане в боте"""
        return choice(cls.BOTBAN_SUCCESS).format(time=time_text)

    @classmethod
    def get_botunban_success(cls) -> str:
        """Возвращает случайное сообщение об успешном разбане в боте"""
        return choice(cls.BOTUNBAN_SUCCESS)


class MuteBanManager:
    """Менеджер модерации с полным функционалом"""

    def __init__(self):
        self.bot = None
        self.bot_ban_manager = BotBanManager(self)
        self.active_mutes = {}
        self.cleanup_task = None

    def set_bot(self, bot):
        """Устанавливает экземпляр бота"""
        self.bot = bot
        self.bot_ban_manager.set_bot(bot)

    # ===== ПРОВЕРКИ ПРАВ =====

    def is_global_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь глобальным админом"""
        return user_id in ADMIN_IDS

    async def _is_bot_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь админом бота (добавленным через админ-панель)"""
        # Глобальные админы всегда имеют доступ
        if self.is_global_admin(user_id):
            return True

        # Проверяем в базе данных
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            is_admin = bool(user and user.is_admin)
            db.close()
            return is_admin
        except Exception as e:
            logger.error(f"Ошибка проверки админа бота: {e}")
            return False

    async def is_chat_admin(self, user_id: int, chat_id: int) -> bool:
        """Проверяет, является ли пользователь админом чата"""
        if not self.bot:
            return False

        try:
            member = await self.bot.get_chat_member(chat_id, user_id)
            return member.status in ["administrator", "creator"]
        except Exception as e:
            logger.error(f"Ошибка проверки админа чата: {e}")
            return False

    async def _is_user_admin(self, user_id: int, chat_id: int = None) -> bool:
        """Проверяет, является ли пользователь администратором"""
        # Глобальные админы
        if self.is_global_admin(user_id):
            return True

        # Админы в БД - ИСПРАВЛЕННАЯ ЧАСТЬ
        try:
            # Используем контекстный менеджер для сессии
            db = None
            try:
                db = next(get_db())
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                is_admin = bool(user and user.is_admin)
                if is_admin:
                    return True
            except Exception as e:
                logger.error(f"Ошибка проверки админа в БД: {e}")
            finally:
                if db:
                    db.close()
        except Exception as e:
            logger.error(f"Ошибка подключения к БД: {e}")

        # Админы чата (если указан chat_id)
        if chat_id and self.bot:
            return await self.is_chat_admin(user_id, chat_id)

        return False

    async def _check_admin(self, message: types.Message) -> bool:
        """Проверяет права администратора у отправителя"""
        if not message or not message.from_user:
            return False
        return await self._is_user_admin(message.from_user.id, message.chat.id if message.chat else None)

    async def _check_bot_admin(self, message: types.Message) -> bool:
        """Проверяет права администратора бота у отправителя"""
        if not message or not message.from_user:
            return False
        return await self._is_bot_admin(message.from_user.id)

    async def _check_bot_permissions(self, chat_id: int) -> bool:
        """Проверяет права бота в чате"""
        if not self.bot:
            return False

        try:
            bot_member = await self.bot.get_chat_member(chat_id, self.bot.id)

            if bot_member.status == "administrator":
                return bot_member.can_restrict_members
            elif bot_member.status == "restricted":
                return hasattr(bot_member, 'can_restrict_members') and bot_member.can_restrict_members
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки прав бота: {e}")
            return False

    async def _check_target_is_admin(self, chat_id: int, user_id: int) -> bool:
        """Проверяет, является ли целевой пользователь админом"""
        # Проверка глобального админа
        if self.is_global_admin(user_id):
            return True

        # Проверка админа чата
        if chat_id:
            return await self.is_chat_admin(user_id, chat_id)

        return False

    async def _check_user_mute_status(self, chat_id: int, user_id: int) -> Optional[bool]:
        """Проверяет статус мута пользователя"""
        if not self.bot:
            return None

        try:
            member = await self.bot.get_chat_member(chat_id, user_id)

            # Если пользователь админ или создатель, у него нет мута
            if member.status in ["administrator", "creator"]:
                return False

            # Если пользователь ограничен, проверяем права
            if member.status == "restricted":
                # В зависимости от версии aiogram, атрибут может называться по-разному
                if hasattr(member, 'can_send_messages'):
                    permissions = member.can_send_messages
                elif hasattr(member, 'permissions'):
                    permissions = member.permissions.can_send_messages
                else:
                    return None
                return not permissions  # True если замучен (не может отправлять сообщения)

            # Если обычный участник или покинувший
            return False

        except Exception as e:
            logger.error(f"Ошибка проверки статуса мута: {e}")
            return None

    # ===== ОСНОВНЫЕ МЕТОДЫ МОДЕРАЦИИ =====

    async def mute_user(self, chat_id: int, user_id: int, admin_id: int,
                        duration_minutes: int = 30, reason: str = "Без причины") -> Tuple[bool, str]:
        """Мутит пользователя. Возвращает (успех, сообщение)"""
        if not self.bot:
            return False, ResponseTexts.ERROR_GENERAL

        try:
            # Проверка админа цели
            if await self.is_chat_admin(user_id, chat_id):
                return False, ResponseTexts.ERROR_ADMIN_TARGET

            # Проверяем, не замучен ли уже пользователь
            mute_status = await self._check_user_mute_status(chat_id, user_id)
            if mute_status is True:
                return False, ResponseTexts.ERROR_ALREADY_MUTED
            elif mute_status is None:
                logger.warning(f"Не удалось проверить статус пользователя {user_id}")

            # Рассчитываем until_date
            if duration_minutes <= 0:
                return False, ResponseTexts.ERROR_INVALID_TIME

            # Преобразуем минуты в секунды для until_date
            until_date = int(time.time()) + (duration_minutes * 60)

            # Минимальное время мута в Telegram - 30 секунд
            if until_date <= int(time.time()) + 30:
                until_date = int(time.time()) + 30

            permissions = types.ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )

            # Используем until_date как timestamp (int)
            await self.bot.restrict_chat_member(chat_id, user_id, permissions, until_date=until_date)

            # Логирование
            try:
                db = next(get_db())
                ModerationLogRepository.add_log(
                    db=db,
                    action=ModerationAction.MUTE,
                    chat_id=chat_id,
                    user_id=user_id,
                    admin_id=admin_id,
                    reason=reason,
                    duration_minutes=duration_minutes
                )
                db.close()
            except Exception as e:
                logger.error(f"Ошибка логирования мута: {e}")

            # Сохранение для авторазмута
            if chat_id not in self.active_mutes:
                self.active_mutes[chat_id] = {}

            # Сохраняем время размута как datetime
            self.active_mutes[chat_id][user_id] = datetime.utcnow() + timedelta(minutes=duration_minutes)

            # Формируем текст времени
            time_text = self._format_duration(duration_minutes)

            logger.info(
                f"Пользователь {user_id} замучен в {chat_id} на {duration_minutes} мин (until_date={until_date})")
            return True, ResponseTexts.get_mute_success(time_text)

        except BadRequest as e:
            error_msg = str(e)
            if "User is an administrator of the chat" in error_msg:
                return False, ResponseTexts.ERROR_ADMIN_TARGET
            elif "Not enough rights" in error_msg or "CHAT_ADMIN_REQUIRED" in error_msg:
                return False, "Недостаточно прав у бота"
            elif "USER_NOT_PARTICIPANT" in error_msg or "User not found" in error_msg:
                return False, "Пользователь не найден в чате"
            elif "Can't remove chat owner" in error_msg:
                return False, "Нельзя мутить создателя чата"
            else:
                logger.error(f"Ошибка мута: {e}")
                return False, f"Ошибка: {error_msg[:100]}"
        except Exception as e:
            logger.error(f"Ошибка мута: {e}")
            return False, ResponseTexts.ERROR_GENERAL

    async def unmute_user(self, chat_id: int, user_id: int, admin_id: int) -> Tuple[bool, str]:
        """Размучивает пользователя. Возвращает (успех, сообщение)"""
        if not self.bot:
            return False, ResponseTexts.ERROR_GENERAL

        try:
            # Проверяем статус пользователя
            mute_status = await self._check_user_mute_status(chat_id, user_id)

            # Если пользователь админ
            if await self.is_chat_admin(user_id, chat_id):
                # Удаляем из активных мутов если был там
                if chat_id in self.active_mutes and user_id in self.active_mutes[chat_id]:
                    del self.active_mutes[chat_id][user_id]
                    if not self.active_mutes[chat_id]:
                        del self.active_mutes[chat_id]
                return False, "Пользователь является администратором"

            # Если статус неизвестен или пользователь замучен - пробуем размутить
            permissions = types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )

            # Устанавливаем права без ограничения времени
            await self.bot.restrict_chat_member(chat_id, user_id, permissions)

            # Удаляем из активных мутов
            if chat_id in self.active_mutes and user_id in self.active_mutes[chat_id]:
                del self.active_mutes[chat_id][user_id]
                if not self.active_mutes[chat_id]:
                    del self.active_mutes[chat_id]

            # Логирование
            try:
                db = next(get_db())
                ModerationLogRepository.add_log(
                    db=db,
                    action=ModerationAction.UNMUTE,
                    chat_id=chat_id,
                    user_id=user_id,
                    admin_id=admin_id,
                    reason="Ручной размут"
                )
                db.close()
            except Exception as e:
                logger.error(f"Ошибка логирования размута: {e}")

            logger.info(f"Пользователь {user_id} размучен в {chat_id}")
            return True, ResponseTexts.get_unmute_success()

        except BadRequest as e:
            error_msg = str(e)
            if "User is an administrator of the chat" in error_msg:
                return False, "Пользователь является администратором"
            elif "Not enough rights" in error_msg or "CHAT_ADMIN_REQUIRED" in error_msg:
                return False, "Недостаточно прав у бота"
            elif "USER_NOT_PARTICIPANT" in error_msg or "User not found" in error_msg:
                return True, "Пользователь не найден в чате"
            elif "Can't remove chat owner" in error_msg:
                return False, "Нельзя размутить создателя чата"
            else:
                logger.error(f"Ошибка размута: {e}")
                return False, f"Ошибка: {error_msg[:100]}"
        except Exception as e:
            logger.error(f"Ошибка размута: {e}")
            return False, ResponseTexts.ERROR_GENERAL

    async def ban_user(self, chat_id: int, user_id: int, admin_id: int,
                       reason: str = "Без причины") -> bool:
        """Банит пользователя (не может вернуться)"""
        if not self.bot:
            return False

        try:
            # Проверка админа цели
            if await self.is_chat_admin(user_id, chat_id):
                logger.warning(f"Попытка бана админа чата {user_id}")
                return False

            # Бан с запретом возвращения
            await self.bot.kick_chat_member(chat_id, user_id)

            # Логирование
            try:
                db = next(get_db())
                ModerationLogRepository.add_log(
                    db=db,
                    action=ModerationAction.BAN,
                    chat_id=chat_id,
                    user_id=user_id,
                    admin_id=admin_id,
                    reason=reason
                )
                db.close()
            except Exception as e:
                logger.error(f"Ошибка логирования бана: {e}")

            logger.info(f"Пользователь {user_id} забанен в {chat_id}")
            return True
        except BadRequest as e:
            if "User is an administrator of the chat" in str(e):
                logger.warning(f"Не удалось забанить админа чата {user_id}")
                return False
            logger.error(f"Ошибка бана: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка бана: {e}")
            return False

    async def unban_user(self, chat_id: int, user_id: int, admin_id: int) -> bool:
        """Разбанивает пользователя"""
        if not self.bot:
            return False

        try:
            await self.bot.unban_chat_member(chat_id, user_id)

            # Логирование
            try:
                db = next(get_db())
                ModerationLogRepository.add_log(
                    db=db,
                    action=ModerationAction.UNBAN,
                    chat_id=chat_id,
                    user_id=user_id,
                    admin_id=admin_id,
                    reason="Ручной разбан"
                )
                db.close()
            except Exception as e:
                logger.error(f"Ошибка логирования разбана: {e}")

            logger.info(f"Пользователь {user_id} разбанен в {chat_id}")
            return True
        except BadRequest as e:
            error_msg = str(e)
            if "USER_NOT_PARTICIPANT" in error_msg or "User not found" in error_msg:
                logger.info(f"Пользователь {user_id} не является участником чата {chat_id}")
                return True
            elif "Not enough rights" in error_msg or "CHAT_ADMIN_REQUIRED" in error_msg:
                logger.warning(f"Недостаточно прав для разбана {user_id} в {chat_id}")
                return False
            else:
                logger.error(f"Ошибка разбана: {e}")
                return False
        except Exception as e:
            logger.error(f"Ошибка разбана: {e}")
            return False

    async def kick_user(self, chat_id: int, user_id: int, admin_id: int,
                        reason: str = "Без причины") -> bool:
        """Кикает пользователя (может вернуться)"""
        if not self.bot:
            return False

        try:
            # Проверка админа цели
            if await self.is_chat_admin(user_id, chat_id):
                logger.warning(f"Попытка кика админа чата {user_id}")
                return False

            # Сначала разбаниваем если забанен
            try:
                await self.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
            except:
                pass

            # Кикаем (удаляем) пользователя без бана
            await self.bot.kick_chat_member(chat_id, user_id)
            # Моментально разрешаем вернуться
            await asyncio.sleep(0.1)
            await self.bot.unban_chat_member(chat_id, user_id)

            # Логирование
            try:
                db = next(get_db())
                ModerationLogRepository.add_log(
                    db=db,
                    action=ModerationAction.KICK,
                    chat_id=chat_id,
                    user_id=user_id,
                    admin_id=admin_id,
                    reason=reason
                )
                db.close()
            except Exception as e:
                logger.error(f"Ошибка логирования кика: {e}")

            logger.info(f"Пользователь {user_id} кикнут из {chat_id}")
            return True
        except BadRequest as e:
            if "User is an administrator of the chat" in str(e):
                logger.warning(f"Не удалось кикнуть админа чата {user_id}")
                return False
            logger.error(f"Ошибка кика: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка кика: {e}")
            return False

    # ===== БАН В БОТЕ =====

    async def check_bot_ban(self, user_id: int) -> bool:
        """Проверяет бан в боте"""
        return self.bot_ban_manager.is_user_bot_banned(user_id)

    async def ban_in_bot(self, user_id: int, admin_id: int,
                         reason: str = "Не указана", seconds: int = None) -> bool:
        """Банит пользователя в боте"""
        # Проверяем, не пытаемся ли забанить админа бота
        if await self._is_bot_admin(user_id):
            logger.warning(f"Попытка бана админа бота: {user_id}")
            return False

        return await self.bot_ban_manager.ban_user_in_bot(user_id, admin_id, reason, seconds)

    async def unban_in_bot(self, user_id: int) -> bool:
        """Разбанивает пользователя в боте"""
        return await self.bot_ban_manager.unban_user_in_bot(user_id)

    async def get_bot_ban_info(self, user_id: int) -> Optional[Dict]:
        """Получает информацию о бане пользователя в боте"""
        return self.bot_ban_manager.get_ban_info(user_id)

    # ===== УТИЛИТЫ =====

    TIME_MULTIPLIERS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}

    def parse_time(self, text: str) -> Optional[dict]:
        """Парсит время из строки"""
        if not text:
            return None

        text = text.lower().strip()

        # Если просто число, считаем что это минуты
        if text.isdigit():
            value = int(text)
            seconds = value * 60  # минуты по умолчанию
            time_text = self._format_duration(value, "m")
            return {'seconds': seconds, 'text': time_text, 'minutes': value, 'unit': 'm'}

        ru_to_en = {'с': 's', 'м': 'm', 'ч': 'h', 'д': 'd', 'н': 'w'}

        for ru, en in ru_to_en.items():
            text = text.replace(ru, en)

        match = re.match(r"^(\d+)([smhdw]?)$", text)
        if not match:
            return None

        value, unit = match.groups()
        value = int(value)

        if not unit:
            unit = 'm'  # По умолчанию минуты

        if unit not in self.TIME_MULTIPLIERS:
            return None

        seconds = value * self.TIME_MULTIPLIERS[unit]
        seconds = min(seconds, 315360000)  # Макс 10 лет

        # Форматируем для отображения
        time_text = self._format_duration(value, unit)

        return {'seconds': seconds, 'text': time_text, 'value': value, 'unit': unit}

    def _format_duration(self, value: int, unit: str = "m") -> str:
        """Форматирует длительность для отображения"""
        unit_display = {
            's': ['секунда', 'секунды', 'секунд'],
            'm': ['минута', 'минуты', 'минут'],
            'h': ['час', 'часа', 'часов'],
            'd': ['день', 'дня', 'дней'],
            'w': ['неделя', 'недели', 'недель']
        }

        if unit not in unit_display:
            return f"{value} мин"

        forms = unit_display[unit]

        if value % 10 == 1 and value % 100 != 11:
            return f"{value} {forms[0]}"
        elif 2 <= value % 10 <= 4 and (value % 100 < 10 or value % 100 >= 20):
            return f"{value} {forms[1]}"
        else:
            return f"{value} {forms[2]}"

    def _extract_time_and_reason(self, text: str) -> Tuple[Optional[int], Optional[str], str]:
        """Извлекает время и причину из текста"""
        if not text:
            return None, None, "Не указана"

        parts = text.strip().split()
        if not parts:
            return None, None, "Не указана"

        # Пробуем распарсить первое слово как время
        time_data = self.parse_time(parts[0])

        if time_data:
            seconds = time_data['seconds']
            time_text = time_data['text']
            reason = ' '.join(parts[1:]) if len(parts) > 1 else "Не указана"
            return seconds, time_text, reason
        else:
            # Если первое слово не время, то всё - причина
            return None, None, text

    # ===== ФОНОВЫЕ ЗАДАЧИ =====

    def start_cleanup_tasks(self):
        """Запускает фоновые задачи"""
        if not self.cleanup_task or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._unmute_scheduler())
        self.bot_ban_manager.start_cleanup_task()

    async def stop_cleanup_tasks(self):
        """Останавливает фоновые задачи"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        await self.bot_ban_manager.stop_cleanup_task()

    async def _unmute_scheduler(self):
        """Автоматический размут"""
        while True:
            try:
                now = datetime.utcnow()
                to_remove = []

                for chat_id, mutes in list(self.active_mutes.items()):
                    for user_id, unmute_time in list(mutes.items()):
                        if now >= unmute_time:
                            try:
                                # Проверяем, замучен ли еще пользователь
                                mute_status = await self._check_user_mute_status(chat_id, user_id)
                                if mute_status is True:
                                    perms = types.ChatPermissions(
                                        can_send_messages=True,
                                        can_send_media_messages=True,
                                        can_send_other_messages=True,
                                        can_add_web_page_previews=True
                                    )
                                    await self.bot.restrict_chat_member(chat_id, user_id, perms)
                                    logger.info(f"Автоматический анмут {user_id} в {chat_id}")
                                else:
                                    logger.info(f"Пользователь {user_id} уже не замучен, пропускаем авторазмут")
                            except Exception as e:
                                logger.warning(f"Не удалось размутить {user_id} в {chat_id}: {e}")
                            to_remove.append((chat_id, user_id))

                for chat_id, user_id in to_remove:
                    self.active_mutes[chat_id].pop(user_id, None)
                    if not self.active_mutes[chat_id]:
                        self.active_mutes.pop(chat_id, None)

                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в планировщике: {e}")
                await asyncio.sleep(60)

    async def restore_mutes_after_restart(self):
        """Восстанавливает муты после перезапуска"""
        logger.info("Восстановление мутов после перезапуска")


# Глобальный экземпляр
mute_ban_manager = MuteBanManager()


# ===== ОБРАБОТЧИКИ КОМАНД =====

async def cmd_mute(message: types.Message):
    """Обработчик команды /mute"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS)
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    # Проверка цели
    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    target_user = message.reply_to_message.from_user

    # Проверка админа цели
    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET)
        return

    # Парсинг времени из аргументов
    args = message.get_args()
    duration_minutes = 30  # По умолчанию 30 минут

    if args:
        time_data = mute_ban_manager.parse_time(args)
        if time_data:
            duration_minutes = time_data['seconds'] // 60
            if duration_minutes < 1:
                duration_minutes = 1  # Минимум 1 минута
            logger.info(f"Парсинг времени '{args}': {duration_minutes} минут")
        else:
            logger.warning(f"Не удалось распарсить время из '{args}'")

    # Выполнение мута
    success, result_message = await mute_ban_manager.mute_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        duration_minutes=duration_minutes,
        reason="Модерация"
    )

    await message.answer(result_message)


async def cmd_unmute(message: types.Message):
    """Обработчик команды /unmute"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS)
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    target_user = message.reply_to_message.from_user

    # Размучиваем
    success, result_message = await mute_ban_manager.unmute_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id
    )

    await message.answer(result_message)


async def cmd_ban(message: types.Message):
    """Обработчик команды /ban"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS)
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET)
        return

    success = await mute_ban_manager.ban_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        reason="Модерация"
    )

    if success:
        await message.answer(ResponseTexts.get_ban_success())
    else:
        await message.answer(ResponseTexts.ERROR_GENERAL)


async def cmd_unban(message: types.Message):
    """Обработчик команды /unban"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS)
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    # Получаем user_id из аргументов или reply
    user_id = None

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        args = message.get_args()
        if args:
            try:
                user_id = int(args)
            except ValueError:
                await message.answer("❌ Укажите ID пользователя или ответьте на сообщение!")
                return

    if not user_id:
        await message.answer("❌ Укажите ID пользователя или ответьте на сообщение!")
        return

    success = await mute_ban_manager.unban_user(
        chat_id=message.chat.id,
        user_id=user_id,
        admin_id=message.from_user.id
    )

    if success:
        await message.answer(ResponseTexts.get_unban_success())
    else:
        await message.answer(ResponseTexts.ERROR_GENERAL)


async def cmd_kick(message: types.Message):
    """Обработчик команды /kick"""
    if not await mute_ban_manager._check_admin(message):
        await message.answer(ResponseTexts.ERROR_NO_RIGHTS)
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET)
        return

    success = await mute_ban_manager.kick_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        reason="Модерация"
    )

    if success:
        await message.answer(ResponseTexts.get_kick_success())
    else:
        await message.answer(ResponseTexts.ERROR_GENERAL)


async def cmd_botban(message: types.Message):
    """Обработчик команды /botban - только для админов бота"""
    # Проверяем что пользователь админ бота
    if not await mute_ban_manager._check_bot_admin(message):
        await message.answer(ResponseTexts.ERROR_BOT_ADMIN_ONLY)
        return

    args = message.get_args()

    # Получение пользователя
    user_id = None
    user_name = "Пользователь"

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_name = message.reply_to_message.from_user.full_name or f"ID {user_id}"
    elif args:
        parts = args.split()
        try:
            user_id = int(parts[0])
            user_name = f"ID {user_id}"
            args = ' '.join(parts[1:]) if len(parts) > 1 else ""
        except ValueError:
            await message.answer("❌ Укажите ID пользователя или ответьте на сообщение!")
            return
    else:
        await message.answer("❌ Использование: /botban [ID/username] [время] [причина] или ответ на сообщение")
        return

    # Проверка админа цели
    if await mute_ban_manager._is_bot_admin(user_id):
        await message.answer(ResponseTexts.ERROR_CANT_BAN_BOT_ADMIN)
        return

    # Парсинг времени и причины
    seconds = None
    time_text = "всегда"
    reason = "Не указана"

    if args:
        seconds, time_text, reason = mute_ban_manager._extract_time_and_reason(args)
        if not seconds:
            time_text = "всегда"

    # Бан в боте
    success = await mute_ban_manager.ban_in_bot(
        user_id=user_id,
        admin_id=message.from_user.id,
        reason=reason,
        seconds=seconds
    )

    if success:
        await message.answer(ResponseTexts.get_botban_success(time_text))
    else:
        await message.answer(ResponseTexts.ERROR_GENERAL)


async def cmd_botunban(message: types.Message):
    """Обработчик команды /botunban - только для админов бота"""
    # Проверяем что пользователь админ бота
    if not await mute_ban_manager._check_bot_admin(message):
        await message.answer(ResponseTexts.ERROR_BOT_ADMIN_ONLY)
        return

    args = message.get_args()

    # Получение пользователя
    user_id = None

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    elif args:
        try:
            user_id = int(args.split()[0])
        except ValueError:
            await message.answer("❌ Укажите ID пользователя или ответьте на сообщение!")
            return
    else:
        await message.answer("❌ Использование: /botunban [ID] или ответ на сообщение")
        return

    # Разбан в боте
    success = await mute_ban_manager.unban_in_bot(user_id)

    if success:
        await message.answer(ResponseTexts.get_botunban_success())
    else:
        await message.answer("❌ Пользователь не был забанен в боте")


# ===== ОБРАБОТЧИКИ ТЕКСТОВЫХ КОМАНД (с поддержкой времени) =====

async def text_mute(message: types.Message):
    """Текстовая команда 'мут' с поддержкой времени"""
    if not message.text or not message.text.lower().startswith('мут'):
        return

    # Проверяем, что это команда мут (возможно с временем)
    text = message.text.lower().strip()
    if not text.startswith('мут'):
        return

    # Проверяем, что это не просто случайный текст, начинающийся с "мут"
    # Допустимые форматы: "мут", "мут 30", "мут 30м", "мут 1ч" и т.д.
    if not (text == 'мут' or re.match(r'^мут\s+\d+[смчдн]?$', text)):
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET)
        return

    # Извлекаем время из команды
    duration_minutes = 30  # По умолчанию 30 минут

    if text != 'мут':
        # Убираем "мут" и пробелы
        time_text = text[3:].strip()
        if time_text:
            time_data = mute_ban_manager.parse_time(time_text)
            if time_data:
                duration_minutes = time_data['seconds'] // 60
                if duration_minutes < 1:
                    duration_minutes = 1
                logger.info(f"Текстовая команда мут '{time_text}': {duration_minutes} минут")
            else:
                logger.warning(f"Не удалось распарсить время из текстовой команды '{time_text}'")

    success, result_message = await mute_ban_manager.mute_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        duration_minutes=duration_minutes,
        reason="Модерация"
    )

    await message.answer(result_message)


async def text_unmute(message: types.Message):
    """Текстовая команда 'размут' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'размут':
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    target_user = message.reply_to_message.from_user

    # Размучиваем
    success, result_message = await mute_ban_manager.unmute_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id
    )

    await message.answer(result_message)


async def text_ban(message: types.Message):
    """Текстовая команда 'бан' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'бан':
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET)
        return

    success = await mute_ban_manager.ban_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        reason="Модерация"
    )

    if success:
        await message.answer(ResponseTexts.get_ban_success())
    else:
        await message.answer(ResponseTexts.ERROR_GENERAL)


async def text_unban(message: types.Message):
    """Текстовая команда 'разбан' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'разбан':
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    # Для команды "разбан" только точное слово - нужно reply
    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    user_id = message.reply_to_message.from_user.id

    success = await mute_ban_manager.unban_user(
        chat_id=message.chat.id,
        user_id=user_id,
        admin_id=message.from_user.id
    )

    if success:
        await message.answer(ResponseTexts.get_unban_success())
    else:
        await message.answer(ResponseTexts.ERROR_GENERAL)


async def text_kick(message: types.Message):
    """Текстовая команда 'кик' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'кик':
        return

    if not await mute_ban_manager._check_admin(message):
        return

    # Проверка прав бота
    if message.chat.type != 'private':
        if not await mute_ban_manager._check_bot_permissions(message.chat.id):
            await message.answer(ResponseTexts.ERROR_BOT_NO_RIGHTS)
            return

    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    target_user = message.reply_to_message.from_user

    if await mute_ban_manager._check_target_is_admin(message.chat.id, target_user.id):
        await message.answer(ResponseTexts.ERROR_ADMIN_TARGET)
        return

    success = await mute_ban_manager.kick_user(
        chat_id=message.chat.id,
        user_id=target_user.id,
        admin_id=message.from_user.id,
        reason="Модерация"
    )

    if success:
        await message.answer(ResponseTexts.get_kick_success())
    else:
        await message.answer(ResponseTexts.ERROR_GENERAL)


async def text_botban(message: types.Message):
    """Текстовая команда 'ботбан' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'ботбан':
        return

    # Проверяем что пользователь админ бота
    if not await mute_ban_manager._check_bot_admin(message):
        await message.answer(ResponseTexts.ERROR_BOT_ADMIN_ONLY)
        return

    # Для команды "ботбан" только точное слово - нужно reply
    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    user_id = message.reply_to_message.from_user.id
    user_name = message.reply_to_message.from_user.full_name or f"ID {user_id}"

    # Проверка админа цели
    if await mute_ban_manager._is_bot_admin(user_id):
        await message.answer(ResponseTexts.ERROR_CANT_BAN_BOT_ADMIN)
        return

    # Бан в боте навсегда (без времени)
    success = await mute_ban_manager.ban_in_bot(
        user_id=user_id,
        admin_id=message.from_user.id,
        reason="Команда ботбан",
        seconds=None
    )

    if success:
        await message.answer(ResponseTexts.get_botban_success("всегда"))
    else:
        await message.answer(ResponseTexts.ERROR_GENERAL)


async def text_botunban(message: types.Message):
    """Текстовая команда 'разботбан' - только точное слово"""
    if not message.text or message.text.lower().strip() != 'разботбан':
        return

    # Проверяем что пользователь админ бота
    if not await mute_ban_manager._check_bot_admin(message):
        await message.answer(ResponseTexts.ERROR_BOT_ADMIN_ONLY)
        return

    # Для команды "разботбан" только точное слово - нужно reply
    if not message.reply_to_message:
        await message.answer(ResponseTexts.ERROR_NO_REPLY)
        return

    user_id = message.reply_to_message.from_user.id

    # Разбан в боте
    success = await mute_ban_manager.unban_in_bot(user_id)

    if success:
        await message.answer(ResponseTexts.get_botunban_success())
    else:
        await message.answer("❌ Пользователь не был забанен в боте")


# ===== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ =====

def register_handlers(dp: Dispatcher):
    """Регистрирует все обработчики"""

    # Проверяем, есть ли бот в менеджере
    if not mute_ban_manager.bot and dp.bot:
        mute_ban_manager.set_bot(dp.bot)
        logger.info("✅ Бот установлен в MuteBanManager при регистрации обработчиков")

    # Слеш-команды (английские)
    dp.register_message_handler(cmd_mute, Command("mute"))
    dp.register_message_handler(cmd_unmute, Command("unmute"))
    dp.register_message_handler(cmd_ban, Command("ban"))
    dp.register_message_handler(cmd_unban, Command("unban"))
    dp.register_message_handler(cmd_kick, Command("kick"))
    dp.register_message_handler(cmd_botban, Command("botban"))
    dp.register_message_handler(cmd_botunban, Command("botunban"))

    # Слеш-команды (русские)
    dp.register_message_handler(cmd_mute, commands=["мут"])
    dp.register_message_handler(cmd_unmute, commands=["размут"])
    dp.register_message_handler(cmd_ban, commands=["бан"])
    dp.register_message_handler(cmd_unban, commands=["разбан"])
    dp.register_message_handler(cmd_kick, commands=["кик"])
    dp.register_message_handler(cmd_botban, commands=["ботбан"])
    dp.register_message_handler(cmd_botunban, commands=["разботбан"])

    # Текстовые команды
    # Для "мут" с поддержкой времени
    dp.register_message_handler(text_mute, lambda m: m.text and m.text.lower().startswith('мут'))
    # Для остальных команд - только точное слово
    dp.register_message_handler(text_unmute, lambda m: m.text and m.text.lower().strip() == 'размут')
    dp.register_message_handler(text_ban, lambda m: m.text and m.text.lower().strip() == 'бан')
    dp.register_message_handler(text_unban, lambda m: m.text and m.text.lower().strip() == 'разбан')
    dp.register_message_handler(text_kick, lambda m: m.text and m.text.lower().strip() == 'кик')
    dp.register_message_handler(text_botban, lambda m: m.text and m.text.lower().strip() == 'ботбан')
    dp.register_message_handler(text_botunban, lambda m: m.text and m.text.lower().strip() == 'разботбан')

    logger.info("✅ Обработчики модерации зарегистрированы (ботбан только для админов бота)")

    # Возвращаем mute_ban_manager для использования в middleware
    return mute_ban_manager


# Инициализация при импорте
try:
    from config import dp, bot

    if bot:
        mute_ban_manager.set_bot(bot)
        logger.info("✅ Бот установлен в MuteBanManager через config")

    logger.info("✅ MuteBanManager готов к использованию")
except ImportError:
    logger.warning("⚠️ Не удалось импортировать из config в handlers/mute_ban.py")
    logger.warning("⚠️ Инициализация будет выполнена позже при регистрации обработчиков")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации mute_ban: {e}")