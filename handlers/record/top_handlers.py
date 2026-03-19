import re
import logging
from typing import List, Tuple
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.crud import ChatRepository, UserRepository
from .record_core import RecordCore


class TopHandlers:
    """Обработчики топов и рейтингов"""

    def __init__(self, record_core: RecordCore):
        self.core = record_core
        self.logger = logging.getLogger(__name__)

    async def show_top_menu(self, message: types.Message, limit: int = 10):
        """Показывает меню выбора топа с 4 кнопками"""
        if not await self.core._check_admin_rights(message):
            await self.core._send_not_admin_message(message)
            return

        keyboard = InlineKeyboardMarkup(row_width=1)

        # Только 4 кнопки как requested
        buttons = [
            InlineKeyboardButton("💰 Топ богатеев", callback_data=f"top_rich_{limit}"),
            InlineKeyboardButton("🏆 Макс. выигрыш", callback_data=f"top_maxwin_{limit}"),
            InlineKeyboardButton("📉 Макс. проигрыш", callback_data=f"top_maxloss_{limit}"),
            InlineKeyboardButton("🎲 Макс. ставка", callback_data=f"top_maxbet_{limit}"),
        ]

        for button in buttons:
            keyboard.add(button)

        await message.reply(f"Какой топ {limit} Вас интересует?", reply_markup=keyboard)

    async def handle_top_callback(self, callback_query: types.CallbackQuery):
        """Обработчик callback'ов для топов"""
        if not await self.core._check_admin_rights(callback_query):
            await self.core._send_not_admin_message(callback_query)
            return

        try:
            chat_id = callback_query.message.chat.id
            user_id = callback_query.from_user.id
            username = callback_query.from_user.username
            first_name = callback_query.from_user.first_name

            await self.core.ensure_user_registered(user_id, chat_id, username, first_name)
            callback_data = callback_query.data

            if callback_data.startswith('top_'):
                parts = callback_data.split('_')
                if len(parts) >= 3 and parts[2].isdigit():
                    top_type = parts[1]
                    limit = int(parts[2])

                    # Ограничиваем максимум 100
                    limit = min(limit, self.core.config.MAX_TOP_LIMIT)

                    type_mapping = {
                        "maxwin": "max_win",
                        "maxloss": "max_loss",
                        "maxbet": "max_bet"
                    }
                    db_top_type = type_mapping.get(top_type, top_type)

                    if db_top_type == "rich":
                        await self._show_rich_top_internal(callback_query, chat_id, user_id, limit)
                    elif db_top_type in ["max_win", "max_loss", "max_bet"]:
                        await self._show_stats_top_internal(callback_query, chat_id, user_id, db_top_type, limit)
                    else:
                        await callback_query.answer("❌ Неизвестный тип топа", show_alert=True)
                    return

            await callback_query.answer("❌ Ошибка обработки запроса", show_alert=True)

        except Exception as e:
            self.logger.error(f"Error in handle_top_callback: {e}")
            await callback_query.answer("❌ Ошибка при получении топа", show_alert=True)

    async def _show_rich_top_internal(self, callback_query: types.CallbackQuery, chat_id: int,
                                      user_id: int, limit: int):
        """Показывает топ богатеев"""
        try:
            with self.core.db_session() as db:
                top_users = ChatRepository.get_top_rich_in_chat(db, chat_id, limit)

                if not top_users:
                    await callback_query.message.edit_text(
                        f"🏆 Пока нет богатеев в этом чате.",
                        reply_markup=None
                    )
                    await callback_query.answer()
                    return

                user_position = ChatRepository.get_user_rank_in_chat(db, chat_id, user_id)
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                user_coins = user.coins if user else 0

                reply_text = f"💰 <b>Топ {limit} богатеев</b>\n"
                reply_text += "━━━━━━━━━━━━━━━\n\n"

                for i, (telegram_id, username, first_name, coins) in enumerate(top_users, start=1):
                    display_name = first_name if first_name else username or "Аноним"
                    if telegram_id == user_id:
                        reply_text += f"🏅 <b>{i}. {display_name} — {coins:,} монет (Вы!)</b>\n"
                    else:
                        reply_text += f"{i}. {display_name} — {coins:,} монет\n"

                # Добавляем позицию пользователя если он не в топе
                if user_position and user_position > limit:
                    reply_text += "\n━━━━━━━━━━━━━━━\n"
                    current_user_name = callback_query.from_user.first_name or callback_query.from_user.username or "Аноним"
                    reply_text += f"<b>{user_position}. {current_user_name} — {user_coins:,} монет</b>"
                elif user_position:
                    reply_text += "\n━━━━━━━━━━━━━━━\n"
                    reply_text += f"<b>🎯 Ваша позиция: #{user_position}</b>"

                await callback_query.message.edit_text(reply_text, parse_mode=types.ParseMode.HTML, reply_markup=None)
                await callback_query.answer()

        except Exception as e:
            self.logger.error(f"Error in _show_rich_top_internal: {e}")
            await callback_query.answer("❌ Ошибка при получении топа богатеев", show_alert=True)

    async def _show_stats_top_internal(self, callback_query: types.CallbackQuery, chat_id: int,
                                       user_id: int, top_type: str, limit: int):
        """Показывает статистические топы"""
        try:
            headers = {
                "max_win": f"🏆 <b>Топ {limit} по максимальному выигрышу</b>\n",
                "max_loss": f"📉 <b>Топ {limit} по максимальному проигрышу</b>\n",
                "max_bet": f"🎲 <b>Топ {limit} по максимальной ставке</b>\n",
            }

            top_methods = {
                "max_win": ChatRepository.get_top_max_win,
                "max_loss": ChatRepository.get_top_max_loss,
                "max_bet": ChatRepository.get_top_max_bet,
            }

            header = headers.get(top_type, f"<b>Топ {limit}</b>\n")
            top_method = top_methods.get(top_type)

            if not top_method:
                await callback_query.answer("❌ Неизвестный тип топа", show_alert=True)
                return

            with self.core.db_session() as db:
                top_data = top_method(db, chat_id, limit)

                if not top_data:
                    await callback_query.message.edit_text(
                        f"🏆 Пока нет данных для этого топа в этом чате.",
                        reply_markup=None
                    )
                    await callback_query.answer()
                    return

                user_position = ChatRepository.get_user_stats_rank(db, chat_id, user_id, top_type)
                reply_text = header
                reply_text += "━━━━━━━━━━━━━━━\n\n"

                for i, (telegram_id, display_name, value) in enumerate(top_data, start=1):
                    if telegram_id == user_id:
                        reply_text += f"🏅 <b>{i}. {display_name} — {value:,}</b>\n"
                    else:
                        reply_text += f"{i}. {display_name} — {value:,}\n"

                user_stats = ChatRepository.get_user_stats(db, user_id, top_type)
                if user_stats is not None:
                    current_user_name = callback_query.from_user.first_name or callback_query.from_user.username or "Аноним"

                    # Добавляем разделитель и позицию пользователя
                    reply_text += "\n━━━━━━━━━━━━━━━\n"
                    if user_position and user_position > limit:
                        reply_text += f"<b>{user_position}. {current_user_name} — {user_stats:,}</b>"
                    else:
                        reply_text += f"<b>🎯 Ваша позиция: #{user_position or '?'}</b>"

                await callback_query.message.edit_text(reply_text, parse_mode=types.ParseMode.HTML, reply_markup=None)
                await callback_query.answer()

        except Exception as e:
            self.logger.error(f"Error in _show_stats_top_internal: {e}")
            await callback_query.answer("❌ Ошибка при получении топа статистики", show_alert=True)

    async def show_rich_top(self, message: types.Message):
        """Обработчик команды 'топ' - показывает меню с кнопками"""
        try:
            command_text = message.text.lower().strip()
            
            # Ищем число после "топ" или "top"
            limit_match = re.search(r'(?:топ|top)\s*(\d+)', command_text)
            
            if limit_match:
                limit = int(limit_match.group(1))
                # Ограничиваем максимум 100
                limit = min(limit, self.core.config.MAX_TOP_LIMIT)
            else:
                # Если число не указано, используем значение по умолчанию
                limit = self.core.config.DEFAULT_TOP_LIMIT

            await self.show_top_menu(message, limit)

        except Exception as e:
            self.logger.error(f"Error in show_rich_top: {e}")
            await message.reply("❌ Ошибка при получении топа.")

    async def show_stats_top(self, message: types.Message):
        """Обработчик статистических топов"""
        if not await self.core._check_admin_rights(message):
            await self.core._send_not_admin_message(message)
            return

        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            username = message.from_user.username
            first_name = message.from_user.first_name
            command_text = message.text.lower().strip()

            await self.core.ensure_user_registered(user_id, chat_id, username, first_name)

            # Ищем число после "топ" или "top"
            limit_match = re.search(r'(?:топ|top)\s*(\d+)', command_text)
            if limit_match:
                limit = min(int(limit_match.group(1)), self.core.config.MAX_TOP_LIMIT)
            else:
                limit = self.core.config.DEFAULT_TOP_LIMIT

            headers = {
                "max_win": f"🏆 <b>Топ {limit} по максимальному выигрышу</b>\n",
                "max_loss": f"📉 <b>Топ {limit} по максимальному проигрышу</b>\n",
                "max_bet": f"🎲 <b>Топ {limit} по максимальной ставке</b>\n",
            }

            top_type = None

            if "макс выигрыш" in command_text:
                top_type = "max_win"
            elif "макс проигрыш" in command_text:
                top_type = "max_loss"
            elif "макс ставка" in command_text:
                top_type = "max_bet"
            else:
                await message.reply("❌ Неизвестный тип топа. Доступные: макс выигрыш, макс проигрыш, макс ставка")
                return

            with self.core.db_session() as db:
                top_methods = {
                    "max_win": ChatRepository.get_top_max_win,
                    "max_loss": ChatRepository.get_top_max_loss,
                    "max_bet": ChatRepository.get_top_max_bet,
                }

                top_data = top_methods[top_type](db, chat_id, limit)

                if not top_data:
                    await message.reply(f"🏆 Пока нет данных для этого топа в этом чате.")
                    return

                user_position = ChatRepository.get_user_stats_rank(db, chat_id, user_id, top_type)
                reply_text = headers[top_type]
                reply_text += "━━━━━━━━━━━━━━━\n\n"

                for i, (telegram_id, display_name, value) in enumerate(top_data, start=1):
                    if telegram_id == user_id:
                        reply_text += f"🏅 <b>{i}. {display_name} — {value:,}</b>\n"
                    else:
                        reply_text += f"{i}. {display_name} — {value:,}\n"

                user_stats = ChatRepository.get_user_stats(db, user_id, top_type)
                if user_stats is not None:
                    current_user_name = first_name or username or "Аноним"

                    reply_text += "\n━━━━━━━━━━━━━━━\n"
                    if user_position and user_position > limit:
                        reply_text += f"<b>{user_position}. {current_user_name} — {user_stats:,}</b>"
                    else:
                        reply_text += f"<b>🎯 Ваша позиция: #{user_position or '?'}</b>"

                await message.reply(reply_text, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            self.logger.error(f"Error in show_stats_top: {e}")
            await message.reply("❌ Ошибка при получении топа статистики.")

    async def show_rich_top_direct(self, message: types.Message):
        """Прямой показ топа богатеев без меню"""
        try:
            chat_id = message.chat.id
            user_id = message.from_user.id
            username = message.from_user.username
            first_name = message.from_user.first_name

            await self.core.ensure_user_registered(user_id, chat_id, username, first_name)

            # Определяем лимит из команды
            command_text = message.text.lower().strip()
            limit_match = re.search(r'(?:топ|top)\s*(\d+)', command_text)

            if limit_match:
                limit = min(int(limit_match.group(1)), self.core.config.MAX_TOP_LIMIT)
            else:
                limit = self.core.config.DEFAULT_TOP_LIMIT

            with self.core.db_session() as db:
                top_users = ChatRepository.get_top_rich_in_chat(db, chat_id, limit)

                if not top_users:
                    await message.reply("🏆 В этом чате пока нет богатеев!")
                    return

                user_position = ChatRepository.get_user_rank_in_chat(db, chat_id, user_id)
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                user_coins = user.coins if user else 0

                reply_text = f"💰 <b>Топ {limit} богатеев</b>\n"
                reply_text += "━━━━━━━━━━━━━━━\n\n"

                for i, (telegram_id, username, first_name, coins) in enumerate(top_users, start=1):
                    display_name = first_name if first_name else username or "Аноним"
                    if telegram_id == user_id:
                        reply_text += f"🏅 <b>{i}. {display_name} — {coins:,} монет (Вы!)</b>\n"
                    else:
                        reply_text += f"{i}. {display_name} — {coins:,} монет\n"

                # Добавляем позицию пользователя если он не в топе
                if user_position and user_position > limit:
                    reply_text += "\n━━━━━━━━━━━━━━━\n"
                    current_user_name = first_name or username or "Аноним"
                    reply_text += f"<b>{user_position}. {current_user_name} — {user_coins:,} монет</b>"
                elif user_position:
                    reply_text += "\n━━━━━━━━━━━━━━━\n"
                    reply_text += f"<b>🎯 Ваша позиция: #{user_position}</b>"

                await message.reply(reply_text, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            self.logger.error(f"Error in show_rich_top_direct: {e}")
            await message.reply("❌ Ошибка при получении топа богатеев.")