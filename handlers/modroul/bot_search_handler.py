# handlers/modroul/bot_search_handler.py
import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.utils.exceptions import MessageToDeleteNotFound, MessageCantBeDeleted

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from database.models import UserChatSearch, UserNickSearch, UserPurchase
from database.crud import ShopRepository, UserRepository

logger = logging.getLogger(__name__)

# Список команд для сбора данных
COMMANDS_TO_LOG = [
    'start', 'help', 'menu', 'settings', 'б',
    'профиль', 'рулетка', 'донат', 'подарки', 'магазин', 'ссылки',
    'баланс', 'топ', 'перевод', 'кража', 'полиция', 'вор', 'кубик'
]

# ID товаров защиты от поиска
PROTECTION_ITEM_IDS = [4]  # ID товаров из магазина


def _sanitize_name(name: str, max_len: int = 100) -> str:
    """Очищает ник от невидимых символов/мусора."""
    if not name:
        return ""
    cleaned = ''.join(
        c for c in str(name).strip()
        if ord(c) >= 32 and c not in ['\u200B', '\uFEFF', '\u2060', '\u0000', '\x00']
    )
    cleaned = cleaned.strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


class BotSearchIdentityMiddleware(BaseMiddleware):
    """
    Middleware: автоматически сохраняет актуальный ник/чат пользователя,
    чтобы история ников была правильной и полной.

    Важно:
    - Не блокирует другие хендлеры
    - Есть троттлинг, чтобы не убивать БД
    - Если ник поменялся — логируем сразу, даже если троттл не прошел
    """

    def __init__(self, handler: "BotSearchHandler", throttle_seconds: int = 60):
        super().__init__()
        self.handler = handler
        self.throttle_seconds = max(5, int(throttle_seconds))
        # (chat_id, user_id) -> (last_ts, last_nick)
        self._last_seen = {}

    async def on_pre_process_message(self, message: types.Message, data: dict):
        try:
            if not message or not message.from_user or message.from_user.is_bot:
                return

            # Сохраняем историю только для групп (как у тебя в логике поиска по чатам)
            if not message.chat or message.chat.type not in ("group", "supergroup"):
                return

            chat_id = message.chat.id
            user_id = message.from_user.id

            # Текущий "видимый ник" из Telegram (быстро, без БД)
            tg_nick = _sanitize_name(message.from_user.full_name or message.from_user.first_name or "")

            now = time.monotonic()
            key = (chat_id, user_id)
            prev = self._last_seen.get(key)

            if prev:
                last_ts, last_nick = prev
                # Если ник не менялся и прошло меньше throttle — не трогаем БД
                if tg_nick == last_nick and (now - last_ts) < self.throttle_seconds:
                    return

            # Обновим кэш сразу (чтобы не спамить)
            self._last_seen[key] = (now, tg_nick)

            # Логируем в БД (внутри — проверка защиты и нормальный ник из БД/бота)
            await self.handler.log_user_identity(message)

        except Exception as e:
            logger.error(f"BotSearchIdentityMiddleware error: {e}")


class BotSearchHandler:
    def __init__(self):
        self.logger = logger
        self.MAX_CHATS = 50
        self.MAX_NICKS = 20
        self.MAX_MESSAGE_LENGTH = 4000
        self.cooldown_dict = {}
        self.cache = {}
        self.CACHE_TTL = 300
        self.stats = {
            'total_searches': 0,
            'data_logged': 0,
            'cache_hits': 0,
            'errors': 0,
            'protected_users': 0,
            'protection_notifications': 0
        }
        self.search_history = {}

    # ------------------------------
    # ✅ Правильный ник как в боте
    # ------------------------------
    def _get_bot_display_name(self, db: Session, tg_user: types.User) -> str:
        """
        Возвращает ник так же, как ты используешь в экономике/топах:
        user.nickname -> user.first_name -> @username -> tg full_name
        """
        try:
            db_user = UserRepository.get_user_by_telegram_id(db, tg_user.id)
        except Exception:
            db_user = None

        # 1) кастомный ник из БД (если есть)
        if db_user and getattr(db_user, "nickname", None):
            nn = _sanitize_name(getattr(db_user, "nickname", ""), max_len=100)
            if nn:
                return nn

        # 2) first_name из БД (если есть)
        if db_user and getattr(db_user, "first_name", None):
            fn = _sanitize_name(getattr(db_user, "first_name", ""), max_len=100)
            if fn:
                return fn

        # 3) username из БД/Telegram
        if db_user and getattr(db_user, "username", None):
            un = _sanitize_name(getattr(db_user, "username", ""), max_len=64)
            if un:
                return f"@{un}"

        if tg_user.username:
            un = _sanitize_name(tg_user.username, max_len=64)
            if un:
                return f"@{un}"

        # 4) Telegram full name fallback
        full = _sanitize_name(tg_user.full_name or tg_user.first_name or "", max_len=100)
        return full if full else "Неизвестно"

    # ------------------------------
    # ✅ Авто-лог ников/чатов
    # ------------------------------
    async def log_user_identity(self, message: types.Message):
        """
        Сохраняет:
        - чат (UserChatSearch) для пользователя
        - ник (UserNickSearch) для истории смен
        Запускается из middleware на любое сообщение.
        """
        try:
            if not message or not message.from_user:
                return

            user_id = message.from_user.id
            chat_id = message.chat.id
            chat_title = getattr(message.chat, "title", "Личные сообщения")

            # Проверяем защиту от поиска
            if self.has_search_protection(user_id, chat_id):
                return

            if not chat_title or len(chat_title) > 255:
                chat_title = "Без названия"

            db = next(get_db())
            try:
                nick = self._get_bot_display_name(db, message.from_user)
                if not nick:
                    nick = "Неизвестно"
                if len(nick) > 255:
                    nick = nick[:255]

                chat_added = self._safe_add_user_chat(db, user_id, chat_id, chat_title)
                nick_added = self._safe_add_user_nick(db, user_id, nick)

                if chat_added or nick_added:
                    db.commit()
                    self.stats['data_logged'] += 1

            except Exception as e:
                db.rollback()
                self.logger.error(f"❌ Database error in log_user_identity: {e}")
                self.stats['errors'] += 1
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"❌ Error in log_user_identity: {e}")
            self.stats['errors'] += 1

    # ------------------------------
    # Твоя отладка защиты
    # ------------------------------
    async def debug_protection_command(self, message: types.Message):
        """Команда для отладки защиты"""
        user_id = message.from_user.id
        chat_id = message.chat.id

        has_protection = self.has_search_protection(user_id, chat_id)

        db = next(get_db())
        try:
            all_purchases = db.query(UserPurchase).filter(
                UserPurchase.user_id == user_id
            ).all()

            protection_purchases = db.query(UserPurchase).filter(
                UserPurchase.user_id == user_id,
                UserPurchase.item_id.in_(PROTECTION_ITEM_IDS)
            ).all()

            active_purchases = ShopRepository.get_active_purchases(db, user_id)

            debug_info = (
                f"🔍 <b>Отладка защиты от поиска:</b>\n\n"
                f"👤 User ID: {user_id}\n"
                f"💬 Chat ID: {chat_id}\n"
                f"🛡️ Защита активна: {'✅ ДА' if has_protection else '❌ НЕТ'}\n\n"
                f"📊 <b>Статистика покупок:</b>\n"
                f"• Всего покупок: {len(all_purchases)}\n"
                f"• Покупок защиты: {len(protection_purchases)}\n"
                f"• Активных покупок: {len(active_purchases)}\n"
                f"• Активные ID: {active_purchases}\n\n"
                f"🛒 <b>Покупки защиты:</b>\n"
            )

            for purchase in protection_purchases:
                status = "✅ АКТИВНА" if (
                        purchase.expires_at is None or purchase.expires_at > datetime.now()) else "❌ ИСТЕКЛА"
                debug_info += f"• ID {purchase.item_id} в чате {purchase.chat_id} - {status}\n"
                debug_info += f"  Срок: {purchase.expires_at}\n"

            await message.reply(debug_info, parse_mode="HTML")

        except Exception as e:
            await message.reply(f"❌ Ошибка отладки: {e}")
        finally:
            db.close()

    def has_search_protection(self, user_id: int, chat_id: int) -> bool:
        """Проверяет, есть ли у пользователя защита от 'бот ищи'"""
        db = next(get_db())
        try:
            for item_id in PROTECTION_ITEM_IDS:
                if ShopRepository.has_active_purchase(db, user_id, item_id):
                    return True

            current_time = datetime.now()
            protection_purchases = db.query(UserPurchase).filter(
                UserPurchase.user_id == user_id,
                UserPurchase.item_id.in_(PROTECTION_ITEM_IDS),
            ).all()

            for purchase in protection_purchases:
                if purchase.expires_at is None or purchase.expires_at > current_time:
                    return True

            return False

        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки защиты: {e}")
            return False
        finally:
            db.close()

    # ------------------------------
    # Лог команд (оставили, но ник теперь правильный)
    # ------------------------------
    async def log_user_command(self, message: types.Message):
        """Логирует только команды пользователя для сбора данных"""
        try:
            if not self._is_command_to_log(message):
                return

            user_id = message.from_user.id
            chat_id = message.chat.id
            chat_title = getattr(message.chat, "title", "Личные сообщения")

            if self.has_search_protection(user_id, chat_id):
                self.logger.info(f"🛡️ Skipping data logging for protected user {user_id} in chat {chat_id}")
                self.stats['protected_users'] += 1
                return

            if not chat_title or len(chat_title) > 255:
                chat_title = "Без названия"

            db = next(get_db())
            try:
                # ✅ Ник берём корректно (как в боте)
                nick = self._get_bot_display_name(db, message.from_user)
                if not nick:
                    nick = "Неизвестно"
                if len(nick) > 255:
                    nick = nick[:255]

                chat_added = self._safe_add_user_chat(db, user_id, chat_id, chat_title)
                nick_added = self._safe_add_user_nick(db, user_id, nick)

                if chat_added or nick_added:
                    db.commit()
                    self.stats['data_logged'] += 1

            except Exception as e:
                db.rollback()
                if "unique constraint" not in str(e).lower() and "duplicate" not in str(e).lower():
                    self.logger.error(f"❌ Database error in log_user_command: {e}")
                    self.stats['errors'] += 1
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"❌ Error in log_user_command: {e}")
            self.stats['errors'] += 1

    # ------------------------------
    # Поиск (бот ищи) — у тебя было ок, оставил
    # ------------------------------
    async def bot_search(self, message: types.Message):
        """Команда 'бот ищи' - показывает информацию о пользователе"""
        try:
            self.stats['total_searches'] += 1
            self.logger.info(f"🔍 Получена команда поиска от {message.from_user.id}: {message.text}")

            if not self._check_cooldown(message.from_user.id, "search"):
                await message.reply("⏳ Подождите 3 секунды перед следующим запросом.")
                return

            target_user = await self._parse_search_target(message)
            if not target_user:
                await self._show_search_help(message)
                return

            user_id = target_user.id
            self.logger.info(f"🎯 Цель поиска: {target_user.full_name} (ID: {user_id})")

            if self.has_search_protection(user_id, message.chat.id):
                await message.reply(
                    f"🛡️ <b>Пользователь защищен от поиска!</b>\n\n"
                    f"👤 <b>{self._escape_html(target_user.full_name)}</b>\n"
                    f"🆔 ID: <code>{user_id}</code>\n\n"
                    f"💡 <i>Информация о пользователе скрыта для вашей безопасности</i>",
                    parse_mode="HTML"
                )
                self._log_search_activity(message.from_user.id, user_id)
                return

            cached_result = self._get_cached_result(user_id)
            if cached_result:
                await message.reply(cached_result, parse_mode="HTML")
                self._log_search_activity(message.from_user.id, user_id)
                return

            search_msg = await message.reply("🔍 <i>Ищем информацию в базе данных...</i>", parse_mode="HTML")

            db = next(get_db())
            try:
                chats = self._get_user_chats_safe(db, user_id)
                nicks = self._get_user_nicks_safe(db, user_id)

                result = self._format_search_result_simple(target_user, chats, nicks, message.from_user.id)
                self._set_cached_result(user_id, result)

                await search_msg.edit_text(result, parse_mode="HTML")
                self._log_search_activity(message.from_user.id, user_id)

            except Exception as e:
                self.logger.error(f"❌ Database error in bot_search: {e}")
                self.stats['errors'] += 1
                await search_msg.edit_text("❌ Произошла ошибка при поиске информации.")
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"❌ Error in bot_search: {e}")
            self.stats['errors'] += 1
            await message.reply("❌ Произошла ошибка при обработке команды.")

    def _get_user_chats_safe(self, db: Session, user_id: int) -> List[Tuple[int, str]]:
        try:
            chats = db.query(UserChatSearch.chat_id, UserChatSearch.chat_title).filter(
                UserChatSearch.user_id == user_id
            ).order_by(UserChatSearch.created_at.desc()).limit(self.MAX_CHATS).all()

            result = []
            for chat_id, chat_title in chats:
                if not chat_title or chat_title.strip() == "":
                    chat_title = f"Чат {chat_id}"
                result.append((chat_id, chat_title))

            return result
        except Exception as e:
            self.logger.error(f"❌ Error getting user chats for {user_id}: {e}")
            return []

    def _get_user_nicks_safe(self, db: Session, user_id: int) -> List[str]:
        """Возвращает уникальные ники (свежие сверху)."""
        try:
            rows = db.query(UserNickSearch.nick).filter(
                UserNickSearch.user_id == user_id
            ).order_by(UserNickSearch.created_at.desc()).limit(self.MAX_NICKS).all()

            raw = [r[0] for r in rows if r and r[0] and str(r[0]).strip()]

            # дедуп (сохраняем порядок)
            seen = set()
            uniq = []
            for n in raw:
                if n not in seen:
                    seen.add(n)
                    uniq.append(n)
            return uniq

        except Exception as e:
            self.logger.error(f"❌ Error getting user nicks for {user_id}: {e}")
            return []

    def _format_search_result_simple(
        self,
        target: types.User,
        chats: List[Tuple[int, str]],
        nicks: List[str],
        searcher_id: int
    ) -> str:
        result = [
            f"🔍 <b>Информация о пользователе:</b>",
            f"👤 <b>{self._escape_html(target.full_name)}</b> (ID: <code>{target.id}</code>)",
            ""
        ]

        if target.username:
            result.append(f"📱 @{target.username}")
            result.append("")

        if chats:
            result.append(f"💬 <b>Чаты пользователя ({len(chats)}):</b>")
            for i, (chat_id, chat_title) in enumerate(chats[:15], 1):
                result.append(f"{i}. {self._escape_html(chat_title)} (ID: <code>{chat_id}</code>)")
            if len(chats) > 15:
                result.append(f"\n📋 <i>... и еще {len(chats) - 15} чатов</i>")
        else:
            result.append("💬 <b>Чаты:</b> не найдено")

        result.append("")

        if nicks:
            result.append(f"📛 <b>История ников ({len(nicks)}):</b>")
            for i, nick in enumerate(nicks[:10], 1):
                result.append(f"{i}. {self._escape_html(nick)}")
            if len(nicks) > 10:
                result.append(f"<i>... и еще {len(nicks) - 10} ников</i>")
        else:
            result.append("📛 <b>Ники:</b> не найдено")

        return "\n".join(result)

    async def _parse_search_target(self, message: types.Message) -> Optional[types.User]:
        try:
            if message.reply_to_message and message.reply_to_message.from_user:
                return message.reply_to_message.from_user

            text = message.text.strip()

            for prefix in ['бот ищи', '!бот ищи', '/ботищи']:
                if text.lower().startswith(prefix.lower()):
                    target_arg = text[len(prefix):].strip()
                    break
            else:
                return None

            if not target_arg:
                return None

            if target_arg.startswith('@'):
                username = target_arg[1:]
                try:
                    user = await message.bot.get_chat(f"@{username}")
                    return user
                except Exception:
                    return None

            elif target_arg.isdigit():
                user_id = int(target_arg)
                try:
                    user = await message.bot.get_chat(user_id)
                    return user
                except Exception:
                    return None

            return None

        except Exception as e:
            self.logger.error(f"❌ Ошибка парсинга цели: {e}")
            return None

    async def _show_search_help(self, message: types.Message):
        help_text = (
            "🔍 <b>Как использовать команду 'бот ищи':</b>\n\n"
            "<b>Способ 1 (рекомендуемый):</b>\n"
            "Ответьте на сообщение пользователя командой:\n"
            "• <code>бот ищи</code>\n"
            "• <code>!бот ищи</code>\n\n"
            "<b>Способ 2:</b>\n"
            "Отправьте команду с ID пользователя:\n"
            "• <code>бот ищи 123456789</code>\n\n"
            "🛡️ <i>Некоторые пользователи могут иметь защиту от поиска</i>\n"
            "📊 <i>Бот покажет информацию о чатах и историю ников пользователя</i>"
        )
        await message.reply(help_text, parse_mode="HTML")

    # ------------------------------
    # Вспомогательные методы (твои)
    # ------------------------------
    def _check_cooldown(self, user_id: int, command: str) -> bool:
        current_time = asyncio.get_event_loop().time()
        key = f"{user_id}_{command}"

        if key in self.cooldown_dict:
            if current_time - self.cooldown_dict[key] < 3:
                return False
        self.cooldown_dict[key] = current_time
        return True

    def _get_cached_result(self, user_id: int) -> Optional[str]:
        if user_id in self.cache:
            result, timestamp = self.cache[user_id]
            current_time = asyncio.get_event_loop().time()
            if current_time - timestamp < self.CACHE_TTL:
                self.stats['cache_hits'] += 1
                return result
            else:
                del self.cache[user_id]
        return None

    def _set_cached_result(self, user_id: int, result: str):
        self.cache[user_id] = (result, asyncio.get_event_loop().time())

    def _log_search_activity(self, searcher_id: int, target_id: int):
        if searcher_id not in self.search_history:
            self.search_history[searcher_id] = []

        now = datetime.now()
        self.search_history[searcher_id] = [
            dt for dt in self.search_history[searcher_id]
            if now - dt < timedelta(hours=1)
        ]
        self.search_history[searcher_id].append(now)

    def _is_command_to_log(self, message: types.Message) -> bool:
        if not message.text:
            return False

        text = message.text.lower().strip()

        search_commands = ['бот ищи', '!бот ищи', '/ботищи', 'бот очисти', 'бот статистика']
        for cmd in search_commands:
            if text.startswith(cmd):
                return False

        for cmd in COMMANDS_TO_LOG:
            cmd_l = cmd.lower()
            if text == cmd_l or text.startswith(cmd_l + ' ') or text.startswith('/' + cmd_l):
                return True

        return False

    def _escape_html(self, text: str) -> str:
        if not text:
            return ""
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    def _safe_add_user_chat(self, db, user_id: int, chat_id: int, chat_title: str) -> bool:
        try:
            existing_count = db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id
            ).count()

            if existing_count >= self.MAX_CHATS:
                records_to_delete = existing_count - self.MAX_CHATS + 1
                oldest_records = db.query(UserChatSearch).filter(
                    UserChatSearch.user_id == user_id
                ).order_by(UserChatSearch.created_at.asc()).limit(records_to_delete).all()

                for record in oldest_records:
                    db.delete(record)

            existing = db.query(UserChatSearch).filter(
                UserChatSearch.user_id == user_id,
                UserChatSearch.chat_id == chat_id
            ).first()

            if not existing:
                record = UserChatSearch(
                    user_id=user_id,
                    chat_id=chat_id,
                    chat_title=chat_title
                )
                db.add(record)
                return True
            elif existing.chat_title != chat_title:
                existing.chat_title = chat_title
                return True

            return False
        except IntegrityError:
            db.rollback()
            return False
        except Exception as e:
            self.logger.error(f"❌ Error in _safe_add_user_chat: {e}")
            return False

    def _safe_add_user_nick(self, db, user_id: int, nick: str) -> bool:
        try:
            existing_count = db.query(UserNickSearch).filter(
                UserNickSearch.user_id == user_id
            ).count()

            if existing_count >= self.MAX_NICKS:
                records_to_delete = existing_count - self.MAX_NICKS + 1
                oldest_records = db.query(UserNickSearch).filter(
                    UserNickSearch.user_id == user_id
                ).order_by(UserNickSearch.created_at.asc()).limit(records_to_delete).all()

                for record in oldest_records:
                    db.delete(record)

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
                return True
            return False
        except IntegrityError:
            db.rollback()
            return False
        except Exception as e:
            self.logger.error(f"❌ Error in _safe_add_user_nick: {e}")
            return False

    async def bot_search_clear(self, message: types.Message):
        try:
            user_id = message.from_user.id
            self.logger.info(f"🧹 Запрос очистки данных от пользователя {user_id}")

            db = next(get_db())
            try:
                chats_deleted = db.query(UserChatSearch).filter(
                    UserChatSearch.user_id == user_id
                ).delete()

                nicks_deleted = db.query(UserNickSearch).filter(
                    UserNickSearch.user_id == user_id
                ).delete()

                db.commit()

                if user_id in self.cache:
                    del self.cache[user_id]

                await message.reply(
                    f"✅ <b>Ваши данные очищены!</b>\n\n"
                    f"🗑️ Удалено:\n"
                    f"• Чатов: {chats_deleted}\n"
                    f"• Ников: {nicks_deleted}\n\n"
                    f"💡 <i>Новые данные будут собираться при следующих сообщениях/командах</i>\n"
                    f"⚡ <i>Кэш также очищен</i>",
                    parse_mode="HTML"
                )

            except Exception as e:
                db.rollback()
                self.logger.error(f"❌ Database error in bot_search_clear: {e}")
                self.stats['errors'] += 1
                await message.reply("❌ Произошла ошибка при очистке данных.")
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"❌ Error in bot_search_clear: {e}")
            self.stats['errors'] += 1
            await message.reply("❌ Произошла ошибка при обработке команды.")

    async def bot_search_stats(self, message: types.Message):
        try:
            stats_text = (
                f"📊 <b>Статистика системы поиска:</b>\n\n"
                f"🔍 Всего поисков: {self.stats['total_searches']}\n"
                f"💾 Данных записано: {self.stats['data_logged']}\n"
                f"⚡ Кэш-попаданий: {self.stats['cache_hits']}\n"
                f"🛡️ Защищенных пользователей: {self.stats['protected_users']}\n"
                f"🔔 Уведомлений о защите: {self.stats['protection_notifications']}\n"
                f"📈 Кэшировано: {len(self.cache)} запросов\n"
                f"❌ Ошибок: {self.stats['errors']}\n\n"
                f"💡 <i>Система работает в штатном режиме</i>"
            )

            await message.reply(stats_text, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"❌ Error in bot_search_stats: {e}")
            await message.reply("❌ Ошибка при получении статистики.")


def register_bot_search_handlers(dp: Dispatcher):
    """Регистрация обработчиков для команды 'бот ищи'"""
    handler = BotSearchHandler()

    logger.info("🔄 Регистрация BotSearchHandler...")

    # ✅ ВАЖНО: включаем middleware истории ников/чатов
    dp.middleware.setup(BotSearchIdentityMiddleware(handler, throttle_seconds=60))

    # 1. Логирование команд для сбора данных (оставляем)
    dp.register_message_handler(
        handler.log_user_command,
        lambda msg: msg.text and handler._is_command_to_log(msg),
        state="*",
        content_types=types.ContentTypes.TEXT,
        run_task=True
    )

    # 2. Команда поиска (основные варианты)
    dp.register_message_handler(
        handler.bot_search,
        Text(startswith='бот ищи', ignore_case=True),
        state="*"
    )

    dp.register_message_handler(
        handler.bot_search,
        Text(startswith='!бот ищи', ignore_case=True),
        state="*"
    )

    # 3. Команда очистки
    dp.register_message_handler(
        handler.bot_search_clear,
        Text(startswith='бот очисти', ignore_case=True),
        state="*"
    )

    # 4. Команда статистики
    dp.register_message_handler(
        handler.bot_search_stats,
        Text(startswith='бот статистика', ignore_case=True),
        state="*"
    )

    # 5. Команда для отладки защиты
    dp.register_message_handler(
        handler.debug_protection_command,
        commands=["debug_protection"],
        state="*"
    )

    logger.info("✅ BotSearchHandler успешно зарегистрирован")
    logger.info(f"📝 Сбор данных включен для {len(COMMANDS_TO_LOG)} команд")
    logger.info(f"🛡️ ID товаров защиты: {PROTECTION_ITEM_IDS}")
