import datetime
import logging
import asyncio
from typing import List, Dict, Optional
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from aiogram import types, Dispatcher
from aiogram.utils.deep_linking import get_start_link

from config import bot
from database import SessionLocal, get_db
from database.crud import UserRepository, ReferenceRepository
from const import START_MENU_TEXT, REFERENCE_MENU_TEXT, LINKS_TEXT
from handlers.modroul.shop import ShopHandler
from handlers.donate import DonateHandler
from handlers.roulette import RouletteHandler
from keyboards.main_menu_kb import main_inline_keyboard, back_to_main_keyboard
from keyboards.reference_keyboard import reference_menu_keyboard
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# МОДЕЛИ ДАННЫХ И КОНФИГУРАЦИЯ
# =============================================================================

@dataclass(frozen=True)
class ReferralConfig:
    """Конфигурация реферальной системы"""
    REFERRER_BONUS: int = 100000  # 100K для пригласившего
    REFERRED_BONUS: int = 20000  # 20K для приглашенного


@dataclass(frozen=True)
class PrivilegeConfig:
    """Конфигурация привилегий"""
    PRIVILEGE_NAMES: Dict[int, str] = None

    def __post_init__(self):
        if self.PRIVILEGE_NAMES is None:
            object.__setattr__(self, 'PRIVILEGE_NAMES', {
                1: "👑 Вор в законе",
                2: "👮‍♂️ Полицейский",
            })


# =============================================================================
# УТИЛИТЫ ДЛЯ ФОРМАТИРОВАНИЯ
# =============================================================================

class UserFormatter:
    """Утилиты для форматирования имен пользователей с ссылками"""

    __slots__ = ()

    def get_original_name(self, user: types.User) -> str:
        """Получает ОРИГИНАЛЬНОЕ имя из Telegram (БЕЗ кастомного ника)"""
        if user.first_name:
            return user.first_name
        elif user.username:
            return f"@{user.username}"
        return "Аноним"

    def get_custom_nickname(self, user_id: int) -> Optional[str]:
        """Получает КАСТОМНЫЙ никнейм пользователя (если установлен)"""
        # Теперь всегда возвращаем None, так как система никнеймов удалена
        return None

    def get_display_name_for_profile(self, user: types.User) -> str:
        """Получает имя для отображения в ПЕРВОЙ СТРОКЕ профиля (всегда оригинальное)"""
        return self.get_original_name(user)

    def get_display_name_for_chat(self, user: types.User) -> str:
        """Получает имя для отображения в чатах (сначала кастомный ник, потом оригинальное)"""
        # Кастомных никнеймов больше нет, всегда используем оригинальное имя
        return self.get_original_name(user)

    def get_display_name(self, user: types.User, use_custom_nickname: bool = True) -> str:
        """
        Получает отображаемое имя пользователя
        """
        # Игнорируем use_custom_nickname, так как система никнеймов удалена
        return self.get_original_name(user)

    @staticmethod
    def get_user_link_html(user_id: int, display_name: str) -> str:
        """Создает HTML-ссылку на профиль пользователя"""
        safe_name = display_name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return f'<a href="tg://user?id={user_id}">{safe_name}</a>'

    def format_user_html(self, user: types.User) -> str:
        """Форматирует объект пользователя с HTML-ссылкой"""
        display_name = self.get_display_name_for_chat(user)
        return self.get_user_link_html(user.id, display_name)

    def format_user_html_original(self, user: types.User) -> str:
        """Форматирует объект пользователя с HTML-ссылкой (всегда оригинальное имя)"""
        display_name = self.get_original_name(user)
        return self.get_user_link_html(user.id, display_name)

    @staticmethod
    def format_user_by_data_html(user_id: int, username: str, first_name: str) -> str:
        """Форматирует пользователя по данным с HTML-ссылкой"""
        display_name = username if username else (first_name if first_name else "Аноним")
        return UserFormatter.get_user_link_html(user_id, display_name)


class DatabaseManager:
    """Менеджер для работы с базой данных"""

    __slots__ = ()

    @staticmethod
    @contextmanager
    def db_session():
        """Контекстный менеджер для БД"""
        db = SessionLocal()
        try:
            db.expire_all()
            yield db
        finally:
            db.close()


# =============================================================================
# СЕРВИСЫ
# =============================================================================

class PrivilegeService:
    """Сервис для работы с привилегиями"""

    __slots__ = ('_config',)

    def __init__(self):
        self._config = PrivilegeConfig()

    def get_privilege_names(self, privilege_ids: List[int]) -> List[str]:
        """Получает названия привилегий по их ID - только Вор и Полицейский"""
        if not privilege_ids:
            return []

        privileges = []
        for privilege_id in privilege_ids:
            if privilege_id in [1, 2]:
                name = self._config.PRIVILEGE_NAMES.get(privilege_id, f"Привилегия #{privilege_id}")
                privileges.append(name)

        return privileges

    @staticmethod
    def format_privileges_text(privileges: List[str]) -> str:
        """Форматирует список привилегий в текст"""
        if not privileges:
            return ""

        unique_privileges = []
        seen_privileges = set()

        for privilege in privileges:
            if privilege not in seen_privileges:
                unique_privileges.append(privilege)
                seen_privileges.add(privilege)

        return "\n".join([f"• {privilege}" for privilege in unique_privileges])


class ReferralService:
    """Сервис для работы с реферальной системой"""

    __slots__ = ('_user_formatter', '_config')

    def __init__(self, user_formatter: UserFormatter):
        self._user_formatter = user_formatter
        self._config = ReferralConfig()

    async def process_referral(self, message: types.Message, payload: str) -> bool:
        """Обработка реферальной ссылки. Возвращает True если реферал обработан"""
        with DatabaseManager.db_session() as db:
            try:
                if ReferenceRepository.check_reference_exists(db, message.from_user.id):
                    return False

                link = await get_start_link(payload=payload)
                owner = UserRepository.get_user_by_link(db, link)
                if not owner:
                    return False

                ReferenceRepository.add_reference(db, owner.telegram_id, message.from_user.id)

                user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)
                if user:
                    user.coins += self._config.REFERRED_BONUS
                    db.commit()

                    asyncio.create_task(self._send_referral_welcome(message.from_user.id, owner.telegram_id))
                    return True

            except Exception as e:
                logging.error(f"❌ Ошибка обработки реферальной ссылки: {e}")
                db.rollback()

            return False

    async def _send_referral_welcome(self, referred_user_id: int, referrer_user_id: int):
        """Отправляет приветственное сообщение рефералу"""
        try:
            db = next(get_db())
            try:
                referred_db_user = UserRepository.get_user_by_telegram_id(db, referred_user_id)
                referrer_db_user = UserRepository.get_user_by_telegram_id(db, referrer_user_id)

                if referred_db_user and referrer_db_user:
                    referred_db_user.coins += self._config.REFERRED_BONUS
                    referrer_db_user.coins += self._config.REFERRER_BONUS
                    db.commit()

                    from aiogram import Bot
                    bot = Bot.get_current()

                    try:
                        referred_user = await bot.get_chat(referred_user_id)
                        referrer_user = await bot.get_chat(referrer_user_id)

                        referrer_name = referrer_user.first_name or referrer_user.username or "пользователь"
                        referred_name = referred_user.first_name or referred_user.username or "пользователь"

                        welcome_text = (
                            f"🎉 Добро пожаловать, {referred_name}!\n\n"
                            f"💎 Вы были приглашены пользователем {referrer_name}\n"
                            f"💰 Вам начислено: {self._config.REFERRED_BONUS:,} монет\n"
                            f"💝 Пригласившему начислено: {self._config.REFERRER_BONUS:,} монет\n\n"
                            f"🎁 Используйте /start для начала работы!"
                        ).replace(",", " ")

                        await bot.send_message(
                            chat_id=referred_user_id,
                            text=welcome_text
                        )

                        notification_text = (
                            f"🎉 По вашей ссылке зарегистрировался новый пользователь!\n\n"
                            f"👤 Новый участник: {referred_name}\n"
                            f"💰 Вам начислено: {self._config.REFERRER_BONUS:,} монет\n"
                            f"💝 Новому пользователю начислено: {self._config.REFERRED_BONUS:,} монет"
                        ).replace(",", " ")

                        await bot.send_message(
                            chat_id=referrer_user_id,
                            text=notification_text
                        )

                        logger.info(f"✅ Реферальное приветствие отправлено пользователю {referred_user_id}")

                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось получить информацию о пользователях из Telegram: {e}")
                        welcome_text = (
                            f"🎉 Добро пожаловать!\n\n"
                            f"💎 Вы были приглашены по реферальной ссылке\n"
                            f"💰 Вам начислено: {self._config.REFERRED_BONUS:,} монет\n"
                            f"💝 Пригласившему начислено: {self._config.REFERRER_BONUS:,} монет\n\n"
                            f"🎁 Используйте /start для начала работы!"
                        ).replace(",", " ")

                        await bot.send_message(
                            chat_id=referred_user_id,
                            text=welcome_text
                        )

            except Exception as e:
                db.rollback()
                logger.error(f"❌ Ошибка при начислении бонусов рефералу: {e}")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"❌ Ошибка отправки приветствия рефералу: {e}")


class ProfileService:
    """Сервис для работы с профилями пользователей"""

    __slots__ = ('_user_formatter', '_privilege_service', '_status_handlers')

    def __init__(self, user_formatter: UserFormatter, privilege_service: PrivilegeService):
        self._user_formatter = user_formatter
        self._privilege_service = privilege_service

        from handlers.status import StatusHandlers
        self._status_handlers = StatusHandlers()

    def format_profile_text(self, user, telegram_user_id: int, privileges: List[str]) -> str:
        """Форматирует текст профиля - показывает оригинальное имя, статус, привилегии и статистику"""

        original_name = self._user_formatter.get_original_name(types.User(
            id=telegram_user_id,
            first_name=user.first_name,
            username=user.username
        ))

        status_text = self._get_user_status_safe(user, telegram_user_id)

        detailed_privileges = self.get_active_privileges_with_expiry(telegram_user_id)

        if detailed_privileges:
            privilege_lines = []
            for priv in detailed_privileges:
                if priv['id'] == 1:
                    privilege_line = f"{priv['name'].replace('👑 ', '').split(' (')[0]} ✵"
                elif priv['id'] == 2:
                    privilege_line = f"{priv['name'].replace('👮‍♂️ ', '').split(' (')[0]}👮‍♂️ "
                else:
                    privilege_line = f"{priv['name'].split(' (')[0]} ✵"
                privilege_lines.append(privilege_line)

            privileges_section = "\n".join(privilege_lines)
        else:
            privileges_section = ""

        profile_lines = [
            f"{original_name}: ♠️♥️",
        ]

        if status_text:
            profile_lines.append(status_text)

        if privileges_section:
            profile_lines.append(privileges_section)

        profile_lines.extend([
            f"Монеты: {user.coins}🪙",
            f"Выиграно: {user.win_coins or 0}",
            f"Проиграно: {user.defeat_coins or 0}",
            f"Макс. выигрыш: {user.max_win_coins or 0}",
            f"Макс. ставка: {getattr(user, 'max_bet', 0)}"
        ])

        return "\n".join(profile_lines)

    def _get_user_status_safe(self, user, telegram_user_id: int) -> str:
        """Безопасное получение статуса пользователя"""
        try:
            status_info = self._status_handlers.get_user_status(telegram_user_id)
            if 'error' not in status_info and status_info.get('has_status'):
                status_display = status_info['status_text']
                if status_display:
                    if len(status_display) > 50:
                        status_display = status_display[:47] + "..."
                    return f"💭 Статус: {status_display}"
        except Exception:
            try:
                if hasattr(user, 'status_text') and user.status_text:
                    status_display = user.status_text
                    if len(status_display) > 50:
                        status_display = status_display[:47] + "..."
                    return f"💭 Статус: {status_display}"
            except Exception:
                pass
        return ""

    def get_user_privileges(self, user_id: int) -> List[str]:
        """Получает список привилегий пользователя (только Вор и Полицейский)"""
        with DatabaseManager.db_session() as db:
            try:
                from sqlalchemy import text
                result = db.execute(
                    text("""
                         SELECT item_id, item_name, expires_at
                         FROM user_purchases
                         WHERE user_id = :user_id
                         """),
                    {"user_id": user_id}
                ).fetchall()

                active_privileges = []
                current_time = datetime.now()

                for item_id, item_name, expires_at in result:
                    if item_id in [1, 2]:
                        if expires_at is None or expires_at > current_time:
                            privilege_name = self._privilege_service._config.PRIVILEGE_NAMES.get(
                                item_id, item_name
                            )
                            active_privileges.append(privilege_name)

                unique_privileges = sorted(list(set(active_privileges)))
                return unique_privileges

            except Exception as e:
                logging.error(f"❌ Ошибка получения привилегий: {e}")
                return []

    def get_active_privileges_with_expiry(self, user_id: int) -> List[Dict]:
        """Получает активные привилегии с информацией о сроке действия (только Вор и Полицейский)"""
        with DatabaseManager.db_session() as db:
            try:
                from sqlalchemy import text
                result = db.execute(
                    text("""
                         SELECT item_id, item_name, expires_at
                         FROM user_purchases
                         WHERE user_id = :user_id
                         """),
                    {"user_id": user_id}
                ).fetchall()

                active_privileges = []
                current_time = datetime.now()

                for item_id, item_name, expires_at in result:
                    if item_id in [1, 2]:
                        if expires_at is None or expires_at > current_time:
                            privilege_name = self._privilege_service._config.PRIVILEGE_NAMES.get(
                                item_id, item_name
                            )

                            time_left_str = ""
                            if expires_at:
                                time_left = expires_at - current_time
                                days_left = time_left.days
                                time_left_str = f" ({days_left} дней)"
                            else:
                                time_left_str = " (навсегда)"

                            active_privileges.append({
                                'id': item_id,
                                'name': privilege_name + time_left_str,
                                'expires_at': expires_at
                            })

                return active_privileges

            except Exception as e:
                logging.error(f"❌ Ошибка получения привилегий с сроком: {e}")
                return []


# =============================================================================
# ОСНОВНЫЕ ОБРАБОТЧИКИ
# =============================================================================

class StartHandlers:
    """Обработчики стартовых команд и меню"""

    __slots__ = ('_user_formatter', '_privilege_service', '_referral_service', '_profile_service')

    def __init__(self):
        self._user_formatter = UserFormatter()
        self._privilege_service = PrivilegeService()
        self._referral_service = ReferralService(self._user_formatter)
        self._profile_service = ProfileService(self._user_formatter, self._privilege_service)

    async def privileges_command(self, message: types.Message):
        """Обработчик команды 'привилегии' - показывает детальную информацию (только Вор и Полицейский)"""
        try:
            with DatabaseManager.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)

                if not user:
                    await message.reply("❌ Профиль не найден")
                    return

                detailed_privileges = self._profile_service.get_active_privileges_with_expiry(message.from_user.id)

                if not detailed_privileges:
                    await message.reply(
                        "💎 Ваши привилегии\n\n"
                        "❌ У вас нет активных привилегий\n\n"
                        "💡 Приобрести привилегии можно:\n"
                        "• Через админа: /admin_help"
                    )
                    return

                privileges_text = "💎 Ваши привилегии\n\n"

                for i, priv in enumerate(detailed_privileges, 1):
                    privileges_text += f"{i}. {priv['name']}\n"

                privileges_text += f"\n📊 Всего активных привилегий: {len(detailed_privileges)}"

                await message.reply(privileges_text)

        except Exception as e:
            logging.error(f"❌ Ошибка в privileges_command: {e}")
            await message.reply("❌ Ошибка загрузки привилегий")

    async def start_button(self, message: types.Message) -> None:
        """Обработчик команды /start"""
        command = message.get_full_command()
        payload = command[1] if len(command) > 1 else None

        referral_processed = False
        if payload:
            referral_processed = await self._referral_service.process_referral(message, payload)

        await self._send_main_menu(message, referral_processed)

    async def _send_main_menu(self, message: types.Message, referral_processed: bool = False) -> None:
        """Отправляет главное меню"""
        try:
            user = types.User(
                id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username
            )
            user_link = self._user_formatter.format_user_html_original(user)
            start_text = START_MENU_TEXT.format(user=user_link).replace('*', '')

            if referral_processed:
                referral_config = ReferralConfig()
                start_text = f"🎉 Вам начислено {referral_config.REFERRED_BONUS:,} монет за переход по реферальной ссылке!\n\n".replace(
                    ",", " ") + start_text

            await bot.send_message(
                chat_id=message.chat.id,
                text=start_text,
                parse_mode=types.ParseMode.HTML,
                reply_markup=main_inline_keyboard()
            )
        except Exception as e:
            logging.error(f"❌ Ошибка в _send_main_menu: {e}")
            await message.answer("❌ Ошибка загрузки меню")

    # ---------- ТЕКСТОВЫЕ КОМАНДЫ ----------

    async def profile_command(self, message: types.Message):
        """Обработчик текстовой команды 'профиль'"""
        try:
            with DatabaseManager.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, message.from_user.id)

                if not user:
                    await message.reply("❌ Профиль не найден")
                    return

                privileges = self._profile_service.get_user_privileges(message.from_user.id)

                profile_text = self._profile_service.format_profile_text(
                    user, message.from_user.id, privileges
                )
                await message.reply(profile_text)

        except Exception as e:
            logging.error(f"❌ Ошибка в profile_command: {e}")
            await message.reply("❌ Ошибка загрузки профиля")

    async def links_command(self, message: types.Message):
        """Обработчик текстовой команды 'ссылки'"""
        try:
            links_text = """💎 EXEZ | GAME ECOSYSTEM

📡 NEWS EXEZ → https://t.me/EXEZ_NEWS
🥂 VIP EXEZ → https://t.me/EXEZ_VIP
💣 NO RULES EXEZ → https://t.me/EXEZ_BEZ
🏆 TOURNAMENTS EXEZ → https://t.me/EXEZ_TUR
⚜️ ZONE EXEZ → https://t.me/EXEZ_ZONE

🌍 Регионы
🇰🇿 KZ EXEZ → https://t.me/EXEZ_KZ
🇰🇬 KG EXEZ → https://t.me/EXEZ_KG

🍀 LUCKY EXEZ → https://t.me/LUCKY_EXEZ"""

            await message.reply(links_text)

        except Exception as e:
            logging.error(f"❌ Ошибка в links_command: {e}")
            await message.reply("❌ Ошибка загрузки ссылок")

    async def id_command(self, message: types.Message):
        """Обработчик команды /id - показывает ID пользователя"""
        try:
            # Определяем, чей ID показывать
            if message.reply_to_message:
                # Если это ответ на сообщение - показываем ID того пользователя
                target_user = message.reply_to_message.from_user
                user_type = "Пользователь"
            else:
                # Иначе показываем ID отправителя команды
                target_user = message.from_user
                user_type = "Ваш ID" if message.chat.type == 'private' else "Пользователь"

            user_id = target_user.id
            user_name = self._user_formatter.get_display_name(target_user)

            # Форматируем ответ
            if message.reply_to_message:
                response = (
                    f"👤 {user_type}: {user_name}\n"
                    f"🆔 ID: <code>{user_id}</code>"
                )
            else:
                if message.chat.type == 'private':
                    response = (
                        f"👤 Ваш профиль: {user_name}\n"
                        f"🆔 Ваш ID: <code>{user_id}</code>"
                    )
                else:
                    response = (
                        f"👤 {user_type}: {user_name}\n"
                        f"🆔 ID: <code>{user_id}</code>\n\n"
                    )

            await message.reply(response, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            logging.error(f"❌ Ошибка в id_command: {e}")
            await message.reply("❌ Ошибка выполнения команды")

    # ---------- INLINE КНОПКИ ----------

    async def profile_button(self, callback: types.CallbackQuery) -> None:
        """Показ профиля через inline кнопку (только Вор и Полицейский)"""
        try:
            with DatabaseManager.db_session() as db:
                user = UserRepository.get_user_by_telegram_id(db, callback.from_user.id)

                if not user:
                    await callback.answer("❌ Профиль не найден", show_alert=True)
                    return

                privileges = self._profile_service.get_user_privileges(callback.from_user.id)

                profile_text = self._profile_service.format_profile_text(
                    user, callback.from_user.id, privileges
                )
                await callback.message.edit_text(profile_text, parse_mode=types.ParseMode.HTML)
                await callback.answer()

        except Exception as e:
            logging.error(f"❌ Ошибка в profile_button: {e}")
            await callback.answer("❌ Ошибка загрузки профиля", show_alert=True)

    async def reference_button(self, callback: types.CallbackQuery) -> None:
        """Показ реферального меню"""
        try:
            with DatabaseManager.db_session() as db:
                referrals_count = ReferenceRepository.get_referrals_count(db, callback.from_user.id)
                reference_text = REFERENCE_MENU_TEXT.format(referrals_count=referrals_count)

                await callback.message.edit_text(
                    text=reference_text,
                    parse_mode=types.ParseMode.MARKDOWN,
                    reply_markup=reference_menu_keyboard()
                )
                await callback.answer()
        except Exception as e:
            logging.error(f"❌ Ошибка в reference_button: {e}")
            await callback.answer("❌ Ошибка загрузки реферального меню", show_alert=True)

    async def links_button(self, callback: types.CallbackQuery) -> None:
        """Показ ссылок через inline кнопку"""
        try:
            links_text = """💎 EXEZ | GAME ECOSYSTEM

📡 NEWS EXEZ → https://t.me/EXEZ_NEWS
🥂 VIP EXEZ → https://t.me/EXEZ_VIP
💣 NO RULES EXEZ → https://t.me/EXEZ_BEZ
🏆 TOURNAMENTS EXEZ → https://t.me/EXEZ_TUR
⚜️ ZONE EXEZ → https://t.me/EXEZ_ZONE

🌍 Регионы
🇰🇿 KZ EXEZ → https://t.me/EXEZ_KZ
🇰🇬 KG EXEZ → https://t.me/EXEZ_KG

🍀 LUCKY EXEZ → https://t.me/LUCKY_EXEZ"""

            await callback.message.edit_text(links_text)
            await callback.answer()
        except Exception as e:
            logging.error(f"❌ Ошибка в links_button: {e}")
            await callback.answer("❌ Ошибка загрузки ссылок", show_alert=True)

    async def shop_button(self, callback: types.CallbackQuery) -> None:
        """Переход в магазин"""
        try:
            shop_handler = ShopHandler()
            await shop_handler.shop_command(callback.message)
            await callback.answer()
        except Exception as e:
            logging.error(f"❌ Ошибка в shop_button: {e}")
            await callback.answer("❌ Ошибка загрузки магазина", show_alert=True)

    async def roulette_button(self, callback: types.CallbackQuery) -> None:
        """Переход в рулетку"""
        try:
            roulette_handler = RouletteHandler()
            await roulette_handler.start_roulette(callback.message)
            await callback.answer()
        except Exception as e:
            logging.error(f"❌ Ошибка в roulette_button: {e}")
            await callback.answer("❌ Ошибка загрузки рулетки", show_alert=True)

    async def stickers_button(self, callback: types.CallbackQuery) -> None:
        """Раздел стикеров"""
        try:
            await callback.message.edit_text(
                "🎭 Раздел стикеров\n\n"
                "📌 В разработке...",
                parse_mode=types.ParseMode.MARKDOWN,
                reply_markup=back_to_main_keyboard()
            )
            await callback.answer()
        except Exception as e:
            logging.error(f"❌ Ошибка в stickers_button: {e}")
            await callback.answer("❌ Ошибка загрузки раздела", show_alert=True)

    async def other_bots_button(self, callback: types.CallbackQuery) -> None:
        """Другие боты"""
        try:
            await callback.message.edit_text(
                "🤖 Другие боты\n\n"
                "📌 В разработке...",
                parse_mode=types.ParseMode.MARKDOWN,
                reply_markup=back_to_main_keyboard()
            )
            await callback.answer()
        except Exception as e:
            logging.error(f"❌ Ошибка в other_bots_button: {e}")
            await callback.answer("❌ Ошибка загрузки раздела", show_alert=True)

    async def donate_button(self, callback: types.CallbackQuery) -> None:
        """Переход к донату"""
        try:
            donate_handler = DonateHandler(bot)
            await donate_handler.donate_command(callback.message)
            await callback.answer()
        except Exception as e:
            logging.error(f"❌ Ошибка в donate_button: {e}")
            await callback.answer("❌ Ошибка загрузки доната", show_alert=True)

    async def agreement_button(self, callback: types.CallbackQuery) -> None:
        """Обработчик кнопки пользовательского соглашения"""
        try:
            file_path = r'media/Пользовательское_Соглашение_EXEZ_кириллица.pdf'

            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            support_keyboard = InlineKeyboardMarkup(row_width=1)
            support_button = InlineKeyboardButton(
                "🛠️ Тех. поддержка",
                url="https://t.me/EXEZTEX"
            )
            back_button = InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
            support_keyboard.add(support_button, back_button)

            with open(file_path, 'rb') as file:
                await bot.send_document(
                    chat_id=callback.message.chat.id,
                    document=file,
                    caption="📄 Пользовательское соглашение\n\n"
                            "🛠️ Если у вас возникли проблемы, обратитесь в техническую поддержку:",
                    reply_markup=support_keyboard
                )
            await callback.answer()
        except FileNotFoundError:
            await callback.answer("❌ Файл соглашения не найден", show_alert=True)
        except Exception as e:
            logging.error(f"❌ Ошибка отправки соглашения: {e}")
            await callback.answer("❌ Ошибка отправки файла", show_alert=True)

    async def support_button(self, callback: types.CallbackQuery) -> None:
        """Обработчик кнопки технической поддержки"""
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            support_keyboard = InlineKeyboardMarkup()
            support_button = InlineKeyboardButton(
                "🛠️ Написать в поддержку",
                url="https://t.me/EXEZTEX"
            )
            back_button = InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")
            support_keyboard.add(support_button, back_button)

            await callback.message.edit_text(
                "🛠️ <b>Техническая поддержка</b>\n\n"
                "Если у вас возникли проблемы с ботом, вопросы по функционалу "
                "или предложения по улучшению - напишите нашему специалисту.\n\n"
                "Мы постараемся помочь вам в кратчайшие сроки! ⚡",
                parse_mode=types.ParseMode.HTML,
                reply_markup=support_keyboard
            )
            await callback.answer()
        except Exception as e:
            logging.error(f"❌ Ошибка в support_button: {e}")
            await callback.answer("❌ Ошибка загрузки информации о поддержке", show_alert=True)

    async def back_to_main_button(self, callback: types.CallbackQuery) -> None:
        """Обработчик кнопки 'Назад в меню'"""
        try:
            await self._send_main_menu_edit(callback.message)
            await callback.answer("Возврат в главное меню")
        except Exception as e:
            logging.error(f"❌ Ошибка в back_to_main_button: {e}")
            await callback.answer("❌ Ошибка возврата в меню", show_alert=True)

    async def _send_main_menu_edit(self, message: types.Message) -> None:
        """Редактирует сообщение и показывает главное меню"""
        try:
            user = types.User(
                id=message.from_user.id,
                first_name=message.from_user.first_name,
                username=message.from_user.username
            )
            user_link = self._user_formatter.format_user_html_original(user)
            start_text = START_MENU_TEXT.format(user=user_link).replace('*', '')

            await message.edit_text(
                text=start_text,
                parse_mode=types.ParseMode.HTML,
                reply_markup=main_inline_keyboard()
            )
        except Exception as e:
            logging.error(f"❌ Ошибка в _send_main_menu_edit: {e}")
            # Если не удалось отредактировать, отправляем новое сообщение
            await self._send_main_menu(message)

    async def faq_button(self, callback: types.CallbackQuery) -> None:
        """Обработчик кнопки FAQ (если нужно логирование или дополнительная обработка)"""
        try:
            # Логируем нажатие
            logger.info(f"Пользователь {callback.from_user.id} открыл FAQ")

            # Можно отправить подтверждение или дополнительное сообщение
            await callback.answer("📚 FAQ открывается в браузере...")

            # URL кнопка автоматически откроет ссылку,
            # но мы могли бы добавить дополнительную логику здесь

        except Exception as e:
            logging.error(f"❌ Ошибка в faq_button: {e}")
            await callback.answer("❌ Ошибка при открытии FAQ", show_alert=True)


# =============================================================================
# РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# =============================================================================

def register_start_handler(dp: Dispatcher) -> None:
    """Регистрация обработчиков стартовых команд"""
    handlers = StartHandlers()

    # Команды
    dp.register_message_handler(handlers.start_button, commands=['start'])
    dp.register_message_handler(handlers.id_command, commands=['id'])

    # Текстовые команды
    dp.register_message_handler(
        handlers.profile_command,
        lambda message: message.text and message.text.strip().lower() == 'профиль'
    )
    dp.register_message_handler(
        handlers.links_command,
        lambda message: message.text and message.text.strip().lower() == 'ссылки'
    )
    dp.register_message_handler(
        handlers.privileges_command,
        lambda message: message.text and message.text.strip().lower() in ['привилегии', 'privileges']
    )

    # inline-кнопки
    callback_handlers = {
        "profile": handlers.profile_button,
        "links": handlers.links_button,
        "reference": handlers.reference_button,
        "shop": handlers.shop_button,
        "roulette": handlers.roulette_button,
        "stickers": handlers.stickers_button,
        "other_bots": handlers.other_bots_button,
        "donate": handlers.donate_button,
        "agreement": handlers.agreement_button,
        "support": handlers.support_button,
        "back_to_main": handlers.back_to_main_button,  # Добавляем обработчик кнопки "Назад"
    }

    for callback_data, handler in callback_handlers.items():
        dp.register_callback_query_handler(
            handler,
            lambda c, data=callback_data: c.data == data
        )

    logging.info("✅ Стартовые обработчики зарегистрированы")