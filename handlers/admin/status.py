# handlers/admin/status.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from contextlib import contextmanager

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from database import SessionLocal
from database.crud import UserRepository

logger = logging.getLogger(__name__)

# Пытаемся использовать общую админ-проверку проекта (если доступна)
try:
    from .admin_helpers import check_admin_sync  # если файл лежит в папке admin
except Exception:
    try:
        from handlers.admin.admin_helpers import check_admin_sync  # если структура handlers/*
    except Exception:
        check_admin_sync = None


# =============================================================================
# МОДЕЛИ СОСТОЯНИЙ И КОНФИГУРАЦИЯ
# =============================================================================

class StatusStates(StatesGroup):
    """Состояния для системы статусов"""
    waiting_for_status = State()   # Ожидание ввода статуса
    editing_status = State()       # Редактирование статуса


class StatusConfig:
    """Конфигурация системы статусов"""

    # Лимиты по длине
    MAX_STATUS_LENGTH = 120
    MIN_STATUS_LENGTH = 1

    # Ограничения по времени
    COOLDOWN_HOURS = 1
    RESET_COOLDOWN = 24

    # Сообщения об ошибках
    ERROR_MESSAGES = {
        'too_long': f"❌ Слишком длинный статус! Максимум {MAX_STATUS_LENGTH} символов.",
        'too_short': "❌ Статус не может быть пустым!",
        'cooldown': "⏳ Вы недавно меняли статус. Попробуйте позже.",
        'invalid_chars': "❌ Статус содержит запрещенные символы!",
        'db_error': "❌ Ошибка базы данных. Попробуйте позже.",
        'success': "✅ Статус успешно сохранен!",
        'cleared': "✅ Статус успешно очищен!",
        'no_status': "📝 У вас еще нет статуса. Используйте /status_set чтобы установить его.",
        'no_permission': "⛔ У вас нет прав для изменения статусов. Эта функция доступна только администраторам.",
        'admin_only': "⛔ Только администраторы могут устанавливать статусы пользователям."
    }

    # Разрешенные символы
    ALLOWED_CHARS = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
        "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
        "0123456789"
        " .,!?@#$%^&*()-_+=:;\"'`~[]{}|\\/<>\n"
        "😀😃😄😁😆😅😂🤣😊😇🙂🙃😉😌😍🥰😘😗😙😚😋😛😝😜🤪🤨🧐🤓😎🤩🥳😏😒😞😔😟😕🙁😣😖😫😩🥺😢😭😤😠😡🤬🤯😳🥵🥶😱😨😰😥😓🤗🤔🤭🤫🤥😶😐😑😬🙄😯😦😧😮😲🥱😴🤤😪😵🤐🥴🤢🤮🤧😷🤒🤕🤑🤠😈👿👹👺🤡💩👻💀☠️👽👾🤖🎃😺😸😹😻😼😽🙀😿😾"
    )

    # Фолбэк-список админов (если нет общей проверки)
    ADMIN_IDS = [6090751674, 987654321]


# =============================================================================
# УТИЛИТЫ ДЛЯ ПРОВЕРКИ ПРАВ И БД
# =============================================================================

class AdminChecker:
    """Класс для проверки прав администратора"""
    __slots__ = ()

    @staticmethod
    def is_admin(user_id: int) -> bool:
        """Проверка админа: через общую систему (если доступна), иначе — через список."""
        try:
            if check_admin_sync:
                return bool(check_admin_sync(user_id))
        except Exception:
            pass
        return user_id in StatusConfig.ADMIN_IDS

    @staticmethod
    def check_admin_permission(user_id: int) -> tuple[bool, Optional[str]]:
        """Проверяет права администратора и возвращает (ok, error_message)."""
        if not AdminChecker.is_admin(user_id):
            return False, StatusConfig.ERROR_MESSAGES['no_permission']
        return True, None


class StatusDatabaseManager:
    """Менеджер для работы с БД статусов"""
    __slots__ = ()

    @staticmethod
    @contextmanager
    def db_session():
        db = SessionLocal()
        try:
            db.expire_all()
            yield db
        finally:
            db.close()

    @staticmethod
    def validate_status_text(text: str) -> tuple[bool, Optional[str]]:
        config = StatusConfig()

        if text is None:
            return False, config.ERROR_MESSAGES['too_short']

        if len(text) < config.MIN_STATUS_LENGTH:
            return False, config.ERROR_MESSAGES['too_short']

        if len(text) > config.MAX_STATUS_LENGTH:
            return False, config.ERROR_MESSAGES['too_long']

        for char in text:
            if char not in config.ALLOWED_CHARS:
                return False, config.ERROR_MESSAGES['invalid_chars']

        return True, None

    @staticmethod
    def can_change_status(last_change: Optional[datetime]) -> tuple[bool, Optional[timedelta]]:
        if last_change is None:
            return True, None

        config = StatusConfig()
        now_utc = datetime.now(timezone.utc)

        if last_change.tzinfo is None:
            last_change_utc = last_change.replace(tzinfo=timezone.utc)
        else:
            last_change_utc = last_change.astimezone(timezone.utc)

        time_since_last_change = now_utc - last_change_utc

        if time_since_last_change < timedelta(hours=config.COOLDOWN_HOURS):
            time_left = timedelta(hours=config.COOLDOWN_HOURS) - time_since_last_change
            return False, time_left

        return True, None

    @staticmethod
    def normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)


# =============================================================================
# СЕРВИСЫ
# =============================================================================

class StatusService:
    """Сервис для работы со статусами"""
    __slots__ = ('_db_manager', '_config')

    def __init__(self):
        self._db_manager = StatusDatabaseManager()
        self._config = StatusConfig()

    def get_user_status(self, user_id: int) -> Dict[str, Any]:
        with self._db_manager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                return {'error': 'Пользователь не найден'}

            status_text = getattr(user, 'status_text', None)
            status_changed_at = getattr(user, 'status_changed_at', None)

            if status_changed_at:
                status_changed_at = self._db_manager.normalize_datetime(status_changed_at)

            return {
                'status_text': status_text,
                'status_changed_at': status_changed_at,
                'has_status': status_text is not None and len(status_text.strip()) > 0
            }

    def set_user_status(self, user_id: int, status_text: str, requester_id: Optional[int] = None) -> tuple[bool, str]:
        # Админ ставит другому
        if requester_id is not None and requester_id != user_id:
            if not AdminChecker.is_admin(requester_id):
                return False, self._config.ERROR_MESSAGES['admin_only']

        # Сам себе — только админ (у тебя так задумано)
        if requester_id is None and not AdminChecker.is_admin(user_id):
            return False, self._config.ERROR_MESSAGES['no_permission']

        is_valid, error_message = self._db_manager.validate_status_text(status_text)
        if not is_valid:
            return False, error_message or self._config.ERROR_MESSAGES['db_error']

        with self._db_manager.db_session() as db:
            try:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    return False, "Пользователь не найден"

                # Кулдаун (если сам себе)
                if requester_id is None or requester_id == user_id:
                    current_time = getattr(user, 'status_changed_at', None)
                    can_change, time_left = self._db_manager.can_change_status(current_time)
                    if not can_change:
                        if time_left:
                            hours = time_left.seconds // 3600
                            minutes = (time_left.seconds % 3600) // 60
                            return False, f"{self._config.ERROR_MESSAGES['cooldown']} (Осталось: {hours}ч {minutes}м)"
                        return False, self._config.ERROR_MESSAGES['cooldown']

                user.status_text = status_text.strip()
                user.status_changed_at = datetime.now(timezone.utc)
                db.commit()
                return True, self._config.ERROR_MESSAGES['success']

            except Exception as e:
                logger.error(f"❌ Ошибка сохранения статуса: {e}", exc_info=True)
                db.rollback()
                return False, self._config.ERROR_MESSAGES['db_error']

    def clear_user_status(self, user_id: int, requester_id: Optional[int] = None) -> tuple[bool, str]:
        if requester_id is not None and requester_id != user_id:
            if not AdminChecker.is_admin(requester_id):
                return False, self._config.ERROR_MESSAGES['admin_only']

        if requester_id is None and not AdminChecker.is_admin(user_id):
            return False, self._config.ERROR_MESSAGES['no_permission']

        with self._db_manager.db_session() as db:
            try:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                if not user:
                    return False, "Пользователь не найден"

                user.status_text = None
                user.status_changed_at = datetime.now(timezone.utc)
                db.commit()
                return True, self._config.ERROR_MESSAGES['cleared']

            except Exception as e:
                logger.error(f"❌ Ошибка очистки статуса: {e}", exc_info=True)
                db.rollback()
                return False, self._config.ERROR_MESSAGES['db_error']

    def format_status_display(self, status_info: Dict[str, Any]) -> str:
        if not status_info.get('has_status'):
            return self._config.ERROR_MESSAGES['no_status']

        status_text = status_info.get('status_text') or ""
        changed_at = status_info.get('status_changed_at')

        if changed_at:
            now_utc = datetime.now(timezone.utc)

            if changed_at.tzinfo is None:
                changed_at_utc = changed_at.replace(tzinfo=timezone.utc)
            else:
                changed_at_utc = changed_at.astimezone(timezone.utc)

            time_diff = now_utc - changed_at_utc
            days = time_diff.days
            hours = time_diff.seconds // 3600

            if days > 0:
                time_str = f"📅 {days} д. назад"
            elif hours > 0:
                time_str = f"🕐 {hours} ч. назад"
            else:
                minutes = (time_diff.seconds % 3600) // 60
                time_str = f"🕐 {minutes} м. назад" if minutes > 0 else "🕐 только что"
        else:
            time_str = "🕐 давно"

        return f"💭 <b>Ваш статус:</b>\n\n{status_text}\n\n{time_str}"

    def get_cooldown_info(self, user_id: int) -> str:
        with self._db_manager.db_session() as db:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                return "Пользователь не найден"

            current_time = getattr(user, 'status_changed_at', None)

            if current_time is None:
                return "✅ Вы можете установить статус прямо сейчас!"

            can_change, time_left = self._db_manager.can_change_status(current_time)
            if can_change:
                return "✅ Вы можете установить статус прямо сейчас!"

            if time_left:
                hours = time_left.seconds // 3600
                minutes = (time_left.seconds % 3600) // 60
                return f"⏳ Следующая смена статуса через: {hours}ч {minutes}м"

            return "⏳ Подождите немного перед следующей сменой статуса"

    def admin_set_status(self, admin_id: int, target_user_id: int, status_text: str) -> tuple[bool, str]:
        if not AdminChecker.is_admin(admin_id):
            return False, self._config.ERROR_MESSAGES['no_permission']
        return self.set_user_status(target_user_id, status_text, requester_id=admin_id)

    def admin_clear_status(self, admin_id: int, target_user_id: int) -> tuple[bool, str]:
        if not AdminChecker.is_admin(admin_id):
            return False, self._config.ERROR_MESSAGES['no_permission']
        return self.clear_user_status(target_user_id, requester_id=admin_id)


# =============================================================================
# ОБРАБОТЧИКИ КОМАНД
# =============================================================================

class StatusHandlers:
    __slots__ = ('_service',)

    def __init__(self):
        self._service = StatusService()

    async def status_command(self, message: types.Message):
        """Показать текущий статус пользователя (/status)"""
        try:
            # ✅ FIX: check_admin_permission принимает user_id, а не message
            ok, err = AdminChecker.check_admin_permission(message.from_user.id)
            if not ok:
                await message.reply(err or StatusConfig.ERROR_MESSAGES['no_permission'])
                return

            status_info = self._service.get_user_status(message.from_user.id)
            if 'error' in status_info:
                await message.reply(f"❌ {status_info['error']}")
                return

            status_text = self._service.format_status_display(status_info)

            if AdminChecker.is_admin(message.from_user.id):
                cooldown_info = self._service.get_cooldown_info(message.from_user.id)
                full_message = f"{status_text}\n\n{cooldown_info}\n\n👑 <b>Вы администратор</b>"
            else:
                full_message = status_text

            await message.reply(full_message, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            logger.error(f"❌ Ошибка в status_command: {e}", exc_info=True)
            await message.reply("❌ Ошибка загрузки статуса")

    async def status_cooldown_command(self, message: types.Message):
        """Показать информацию о кулдауне (/status_cooldown)"""
        try:
            if not AdminChecker.is_admin(message.from_user.id):
                await message.reply(StatusConfig.ERROR_MESSAGES['no_permission'])
                return

            cooldown_info = self._service.get_cooldown_info(message.from_user.id)
            await message.reply(cooldown_info)

        except Exception as e:
            logger.error(f"❌ Ошибка в status_cooldown_command: {e}", exc_info=True)
            await message.reply("❌ Ошибка получения информации о кулдауне")

    async def status_set_command(self, message: types.Message, state: FSMContext):
        """Начать установку статуса (/status_set)"""
        try:
            if not AdminChecker.is_admin(message.from_user.id):
                await message.reply(StatusConfig.ERROR_MESSAGES['no_permission'])
                return

            status_info = self._service.get_user_status(message.from_user.id)
            if 'error' not in status_info and status_info.get('status_changed_at'):
                can_change, time_left = StatusDatabaseManager.can_change_status(status_info['status_changed_at'])
                if not can_change:
                    if time_left:
                        hours = time_left.seconds // 3600
                        minutes = (time_left.seconds % 3600) // 60
                        await message.reply(f"⏳ Вы недавно меняли статус. Попробуйте через {hours}ч {minutes}м.")
                    else:
                        await message.reply("⏳ Вы недавно меняли статус. Попробуйте позже.")
                    return

            config = StatusConfig()
            await message.reply(
                f"📝 <b>Введите ваш новый статус:</b>\n\n"
                f"• Максимум {config.MAX_STATUS_LENGTH} символов\n"
                f"• Можно использовать эмодзи\n"
                f"• Кулдаун между сменами: {config.COOLDOWN_HOURS} час(а)\n\n"
                f"<i>Для отмены отправьте /cancel</i>",
                parse_mode=types.ParseMode.HTML
            )

            await StatusStates.waiting_for_status.set()
            await state.update_data(user_id=message.from_user.id)

        except Exception as e:
            logger.error(f"❌ Ошибка в status_set_command: {e}", exc_info=True)
            await message.reply("❌ Ошибка начала установки статуса")

    async def put_status_command(self, message: types.Message):
        """Поставить статус через команду 'поставить статус <текст>'"""
        try:
            if not AdminChecker.is_admin(message.from_user.id):
                await message.reply(StatusConfig.ERROR_MESSAGES['no_permission'])
                return

            text = (message.text or "").strip()
            if text.lower() == 'поставить статус':
                await message.reply(
                    f"📝 <b>Используйте команду с текстом статуса:</b>\n\n"
                    f"<code>поставить статус ваш текст здесь</code>\n\n"
                    f"• Максимум {StatusConfig.MAX_STATUS_LENGTH} символов\n"
                    f"• Можно использовать эмодзи\n"
                    f"• Кулдаун между сменами: {StatusConfig.COOLDOWN_HOURS} час(а)",
                    parse_mode=types.ParseMode.HTML
                )
                return

            if text.lower().startswith('поставить статус '):
                status_text = text[18:].strip()
            elif text.lower().startswith('/поставить_статус '):
                status_text = text[18:].strip()
            else:
                await message.reply(
                    "❌ Неверный формат команды. Используйте: <code>поставить статус ваш текст</code>",
                    parse_mode=types.ParseMode.HTML
                )
                return

            if not status_text:
                await message.reply("❌ Статус не может быть пустым!")
                return

            status_info = self._service.get_user_status(message.from_user.id)
            if 'error' not in status_info and status_info.get('status_changed_at'):
                can_change, time_left = StatusDatabaseManager.can_change_status(status_info['status_changed_at'])
                if not can_change:
                    if time_left:
                        hours = time_left.seconds // 3600
                        minutes = (time_left.seconds % 3600) // 60
                        await message.reply(f"⏳ Вы недавно меняли статус. Попробуйте через {hours}ч {minutes}м.")
                    else:
                        await message.reply("⏳ Вы недавно меняли статус. Попробуйте позже.")
                    return

            success, result_message = self._service.set_user_status(
                message.from_user.id,
                status_text,
                requester_id=message.from_user.id
            )
            await message.reply(result_message)

            if success:
                status_info = self._service.get_user_status(message.from_user.id)
                if 'error' not in status_info:
                    status_display = self._service.format_status_display(status_info)
                    await message.answer(status_display, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            logger.error(f"❌ Ошибка в put_status_command: {e}", exc_info=True)
            await message.reply("❌ Ошибка установки статуса")

    async def status_edit_command(self, message: types.Message, state: FSMContext):
        """Редактировать статус (/status_edit)"""
        try:
            if not AdminChecker.is_admin(message.from_user.id):
                await message.reply(StatusConfig.ERROR_MESSAGES['no_permission'])
                return

            status_info = self._service.get_user_status(message.from_user.id)
            if 'error' in status_info:
                await message.reply(f"❌ {status_info['error']}")
                return

            if not status_info.get('has_status'):
                await message.reply("❌ У вас еще нет статуса для редактирования. Используйте /status_set")
                return

            config = StatusConfig()
            await message.reply(
                f"✏️ <b>Редактирование статуса:</b>\n\n"
                f"<i>Текущий статус:</i>\n{status_info['status_text']}\n\n"
                f"• Максимум {config.MAX_STATUS_LENGTH} символов\n"
                f"• Кулдаун между сменами: {config.COOLDOWN_HOURS} час(а)\n\n"
                f"<i>Введите новый текст статуса или /cancel для отмены:</i>",
                parse_mode=types.ParseMode.HTML
            )

            await StatusStates.editing_status.set()
            await state.update_data(user_id=message.from_user.id)

        except Exception as e:
            logger.error(f"❌ Ошибка в status_edit_command: {e}", exc_info=True)
            await message.reply("❌ Ошибка начала редактирования статуса")

    async def status_clear_command(self, message: types.Message):
        """Очистить статус (/status_clear)"""
        try:
            if not AdminChecker.is_admin(message.from_user.id):
                await message.reply(StatusConfig.ERROR_MESSAGES['no_permission'])
                return

            success, message_text = self._service.clear_user_status(
                message.from_user.id,
                requester_id=message.from_user.id
            )
            await message.reply(message_text)

        except Exception as e:
            logger.error(f"❌ Ошибка в status_clear_command: {e}", exc_info=True)
            await message.reply("❌ Ошибка очистки статуса")

    async def admin_set_status_command(self, message: types.Message, state: FSMContext):
        """Администратор устанавливает статус другому пользователю (/admin_set_status)"""
        try:
            if not AdminChecker.is_admin(message.from_user.id):
                await message.reply(StatusConfig.ERROR_MESSAGES['no_permission'])
                return

            args = message.get_args()
            if not args:
                await message.reply(
                    "📝 <b>Использование:</b>\n"
                    "<code>/admin_set_status [ID_пользователя] [текст статуса]</code>\n\n"
                    "Пример:\n"
                    "<code>/admin_set_status 123456789 Новый статус пользователя</code>",
                    parse_mode=types.ParseMode.HTML
                )
                return

            parts = args.split(maxsplit=1)
            if len(parts) < 2:
                await message.reply(
                    "❌ Неверный формат. Используйте:\n"
                    "<code>/admin_set_status ID_пользователя текст статуса</code>",
                    parse_mode=types.ParseMode.HTML
                )
                return

            user_id_str, status_text = parts
            try:
                user_id = int(user_id_str)
            except ValueError:
                await message.reply("❌ ID пользователя должен быть числом")
                return

            success, result_message = self._service.admin_set_status(
                message.from_user.id,
                user_id,
                status_text
            )

            if success:
                await message.reply(f"✅ Статус пользователя {user_id} успешно установлен:\n\n{status_text}")
            else:
                await message.reply(f"❌ Ошибка: {result_message}")

        except Exception as e:
            logger.error(f"❌ Ошибка в admin_set_status_command: {e}", exc_info=True)
            await message.reply("❌ Ошибка установки статуса")

    async def admin_clear_status_command(self, message: types.Message):
        """Администратор очищает статус другому пользователю (/admin_clear_status)"""
        try:
            if not AdminChecker.is_admin(message.from_user.id):
                await message.reply(StatusConfig.ERROR_MESSAGES['no_permission'])
                return

            user_id_str = message.get_args()
            if not user_id_str:
                await message.reply(
                    "📝 <b>Использование:</b>\n"
                    "<code>/admin_clear_status [ID_пользователя]</code>\n\n"
                    "Пример:\n"
                    "<code>/admin_clear_status 123456789</code>",
                    parse_mode=types.ParseMode.HTML
                )
                return

            try:
                user_id = int(user_id_str)
            except ValueError:
                await message.reply("❌ ID пользователя должен быть числом")
                return

            success, result_message = self._service.admin_clear_status(
                message.from_user.id,
                user_id
            )

            if success:
                await message.reply(f"✅ Статус пользователя {user_id} успешно очищен")
            else:
                await message.reply(f"❌ Ошибка: {result_message}")

        except Exception as e:
            logger.error(f"❌ Ошибка в admin_clear_status_command: {e}", exc_info=True)
            await message.reply("❌ Ошибка очистки статуса")

    async def process_status_input(self, message: types.Message, state: FSMContext):
        """Обработка введенного статуса"""
        try:
            data = await state.get_data()
            user_id = data.get('user_id', message.from_user.id)

            if message.text and message.text.strip() == '/cancel':
                await state.finish()
                await message.reply("❌ Установка статуса отменена")
                return

            if not AdminChecker.is_admin(message.from_user.id):
                await message.reply(StatusConfig.ERROR_MESSAGES['no_permission'])
                await state.finish()
                return

            success, result_message = self._service.set_user_status(
                user_id,
                message.text or "",
                requester_id=message.from_user.id
            )

            await message.reply(result_message)

            if success:
                status_info = self._service.get_user_status(user_id)
                if 'error' not in status_info:
                    status_display = self._service.format_status_display(status_info)
                    await message.answer(status_display, parse_mode=types.ParseMode.HTML)

            await state.finish()

        except Exception as e:
            logger.error(f"❌ Ошибка обработки статуса: {e}", exc_info=True)
            await message.reply("❌ Ошибка сохранения статуса")
            await state.finish()

    async def cancel_status_setup(self, message: types.Message, state: FSMContext):
        await state.finish()
        await message.reply("❌ Установка статуса отменена")

    def get_formatted_status_for_profile(self, user_id: int) -> str:
        status_info = self._service.get_user_status(user_id)
        if 'error' in status_info or not status_info.get('has_status'):
            return ""
        status_text = status_info['status_text']
        if len(status_text) > 50:
            status_text = status_text[:47] + "..."
        return f"💭 Статус: {status_text}"

    def get_detailed_status_for_profile(self, user_id: int) -> str:
        status_info = self._service.get_user_status(user_id)
        if 'error' in status_info or not status_info.get('has_status'):
            return "📝 Статус: не установлен"

        status_text = status_info['status_text']
        changed_at = status_info.get('status_changed_at')

        if changed_at:
            now_utc = datetime.now(timezone.utc)
            if changed_at.tzinfo is None:
                changed_at_utc = changed_at.replace(tzinfo=timezone.utc)
            else:
                changed_at_utc = changed_at.astimezone(timezone.utc)

            time_diff = now_utc - changed_at_utc
            if time_diff.days > 0:
                time_str = f"{time_diff.days} д. назад"
            else:
                hours = time_diff.seconds // 3600
                time_str = f"{hours} ч. назад" if hours > 0 else "менее часа назад"
        else:
            time_str = "давно"

        display_text = status_text if len(status_text) <= 100 else status_text[:97] + "..."
        return f"💭 Статус: {display_text}\n   📅 Изменен: {time_str}"


# =============================================================================
# РЕГИСТРАЦИЯ
# =============================================================================

def register_status_handlers(dp: Dispatcher) -> None:
    handlers = StatusHandlers()

    dp.register_message_handler(handlers.status_command, commands=['status'])
    dp.register_message_handler(handlers.status_set_command, commands=['status_set'], state=None)
    dp.register_message_handler(handlers.put_status_command, commands=['поставить_статус', 'поставитьстатус'])
    dp.register_message_handler(handlers.status_edit_command, commands=['status_edit'], state=None)
    dp.register_message_handler(handlers.status_clear_command, commands=['status_clear'])
    dp.register_message_handler(handlers.status_cooldown_command, commands=['status_cooldown'])

    dp.register_message_handler(handlers.admin_set_status_command, commands=['admin_set_status'], state=None)
    dp.register_message_handler(handlers.admin_clear_status_command, commands=['admin_clear_status'])

    dp.register_message_handler(
        handlers.status_command,
        lambda message: message.text and message.text.strip().lower() == 'статус'
    )

    dp.register_message_handler(
        handlers.status_set_command,
        lambda message: message.text and message.text.strip().lower() in ['установить статус', 'статус установить'],
        state=None
    )

    dp.register_message_handler(
        handlers.put_status_command,
        lambda message: message.text and message.text.strip().lower().startswith('поставить статус'),
        state=None
    )

    dp.register_message_handler(
        handlers.status_edit_command,
        lambda message: message.text and message.text.strip().lower() in ['редактировать статус', 'изменить статус'],
        state=None
    )

    dp.register_message_handler(
        handlers.status_clear_command,
        lambda message: message.text and message.text.strip().lower() in ['очистить статус', 'удалить статус']
    )

    dp.register_message_handler(
        handlers.process_status_input,
        state=[StatusStates.waiting_for_status, StatusStates.editing_status]
    )

    dp.register_message_handler(
        handlers.cancel_status_setup,
        commands=['cancel'],
        state=[StatusStates.waiting_for_status, StatusStates.editing_status]
    )

    logger.info("✅ Обработчики статусов зарегистрированы")
