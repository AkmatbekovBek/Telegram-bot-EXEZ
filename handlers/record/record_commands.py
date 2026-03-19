import re
import logging
from aiogram import types, Dispatcher

from .record_core import RecordCore
from .top_handlers import TopHandlers
from .services import RecordService
from .auto_top_middleware import AutoTopMiddleware


# чтобы middleware не подключался дважды (если вдруг register_* вызовут повторно)
_AUTO_TOP_MW_INSTALLED = False


class RecordCommands:
    """Команды для работы с рекордами"""

    def __init__(self):
        self.core = RecordCore()
        self.top_handlers = TopHandlers(self.core)
        self.service = RecordService(self.core)
        self.logger = logging.getLogger(__name__)

    # =============================================
    # 🔥 ГЛОБАЛЬНЫЕ РЕКОРДЫ ДНЯ
    # =============================================

    async def check_daily_record(self, message: types.Message):
        """Показывает глобальный рекорд дня - 2 выигрыша + 1 проигрыш"""
        try:
            user_id = message.from_user.id
            username = message.from_user.username
            first_name = message.from_user.first_name

            await self.core.ensure_user_registered(user_id, 0, username, first_name)

            # Получаем 2 лучших выигрыша и 1 лучший проигрыш
            top_wins = self.core._get_global_top_wins_today(2)  # 2 места выигрышей
            top_losses = self.core._get_global_top_losses_today(1)  # 1 место проигрышей

            reply_text = "💰 <b>Глобальный рекорд дня (топ 3)</b>\n"
            reply_text += "━━━━━━━━━━━━━━━━━\n\n"

            medals = ["🥇", "🥈", "🥉"]

            # 🔥 ПЕРВОЕ МЕСТО - выигрыш
            if len(top_wins) > 0:
                user_id1, clickable_name1, amount1 = top_wins[0]  # УЖЕ кликабельное имя
                reply_text += f"{medals[0]} {clickable_name1} — {amount1:,} монет (рекорд выигрыша)\n"
            else:
                reply_text += f"{medals[0]} Пока нет рекорда выигрыша\n"

            # 🔥 ВТОРОЕ МЕСТО - выигрыш
            if len(top_wins) > 1:
                user_id2, clickable_name2, amount2 = top_wins[1]  # УЖЕ кликабельное имя
                reply_text += f"{medals[1]} {clickable_name2} — {amount2:,} монет (рекорд выигрыша)\n"
            else:
                reply_text += f"{medals[1]} Пока нет рекорда выигрыша\n"

            # 🔥 ТРЕТЬЕ МЕСТО - проигрыш
            if top_losses:
                loss_user_id, clickable_loss_name, loss_amount = top_losses[0]  # УЖЕ кликабельное имя
                reply_text += f"{medals[2]} {clickable_loss_name} — {loss_amount:,} монет (рекорд проигрыша)\n"
            else:
                reply_text += f"{medals[2]} Пока нет рекорда проигрыша\n"

            await message.reply(reply_text, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            self.logger.error(f"Error in check_daily_record: {e}")
            await message.reply("❌ Ошибка при получении рекордов.")

    # =============================================
    # 🏅 ПОЗИЦИЯ ПОЛЬЗОВАТЕЛЯ В ТОПЕ
    # =============================================

    async def show_my_position(self, message: types.Message):
        """Показывает позицию пользователя в топе без команды 'топ'"""
        try:
            user_id = message.from_user.id
            chat_id = message.chat.id

            # Регистрируем пользователя при запросе позиции
            await self.service.register_user_for_chat_top(
                user_id, chat_id,
                message.from_user.username,
                message.from_user.first_name
            )

            position_data = self.service.get_user_position_in_chat(user_id, chat_id)

            if position_data['position'] is None:
                await message.reply(
                    "📊 Вы еще не в топе этого чата. Напишите любое сообщение для автоматической регистрации!"
                )
                return

            reply_text = f"🏅 <b>Ваша позиция в топе</b>\n"
            reply_text += "━━━━━━━━━━━━━━━━━\n\n"
            reply_text += f"📍 Позиция: <b>#{position_data['position']}</b>\n"
            reply_text += f"💰 Баланс: <b>{position_data['coins']:,} монет</b>\n\n"

            if position_data['top_5']:
                reply_text += "━━━━━━━━━━━━━━━━━\n"
                reply_text += "<b>Топ-5 чата:</b>\n\n"

                for i, (telegram_id, username, first_name, coins) in enumerate(position_data['top_5'], start=1):
                    display_name = first_name if first_name else username or "Аноним"
                    if telegram_id == user_id:
                        reply_text += f"🏅 <b>{i}. {display_name} — {coins:,} монет (Вы!)</b>\n"
                    else:
                        reply_text += f"{i}. {display_name} — {coins:,} монет\n"

            await message.reply(reply_text, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            self.logger.error(f"Error in show_my_position: {e}")
            await message.reply("❌ Ошибка при получении позиции")

    # =============================================
    # ⚡ БЫСТРЫЙ ТОП ЧАТА
    # =============================================

    async def handle_quick_top(self, message: types.Message):
        """Быстрый топ - показывает топ чата с выделением пользователя"""
        try:
            user_id = message.from_user.id
            chat_id = message.chat.id

            await self.service.register_user_for_chat_top(
                user_id, chat_id,
                message.from_user.username,
                message.from_user.first_name
            )

            position_data = self.service.get_user_position_in_chat(user_id, chat_id)

            if not position_data['top_5']:
                await message.reply("🏆 В этом чате пока нет богатеев!")
                return

            reply_text = "💰 <b>Топ богатеев чата</b>\n"
            reply_text += "━━━━━━━━━━━━━━━━━\n\n"

            with self.core.db_session() as db:
                from database.crud import ChatRepository
                top_users = ChatRepository.get_top_rich_in_chat(db, chat_id, 10)

                for i, (telegram_id, username, first_name, coins) in enumerate(top_users, start=1):
                    display_name = first_name if first_name else username or "Аноним"
                    if telegram_id == user_id:
                        reply_text += f"🏅 <b>{i}. {display_name} — {coins:,} монет (Вы!)</b>\n"
                    else:
                        reply_text += f"{i}. {display_name} — {coins:,} монет\n"

            if position_data['position'] and position_data['position'] > 10:
                current_user_name = message.from_user.first_name or message.from_user.username or "Аноним"
                reply_text += "\n━━━━━━━━━━━━━━━━━\n"
                reply_text += f"<b>{position_data['position']}. {current_user_name} — {position_data['coins']:,} монет</b>"

            await message.reply(reply_text, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            self.logger.error(f"Error in handle_quick_top: {e}")
            await message.reply("❌ Ошибка при получении топа.")

    # =============================================
    # 📊 СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ
    # =============================================

    async def show_user_stats(self, message: types.Message):
        """Показывает статистику пользователя"""
        try:
            user_id = message.from_user.id

            await self.service.register_user_for_chat_top(
                user_id, message.chat.id,
                message.from_user.username,
                message.from_user.first_name
            )

            stats = self.service.get_daily_record_stats(user_id)

            current_user_name = message.from_user.first_name or message.from_user.username or "Аноним"
            clickable_name = self.core._get_user_profile_link(user_id, current_user_name)

            reply_text = f"📊 <b>Статистика {clickable_name}</b>\n"
            reply_text += "━━━━━━━━━━━━━━━━━\n\n"
            reply_text += f"💰 Баланс: <b>{stats['current_balance']:,} монет</b>\n\n"

            reply_text += "━━━━━━━━━━━━━━━━━\n"
            reply_text += "<b>Рекорды сегодня:</b>\n\n"

            if stats['win_amount'] > 0:
                reply_text += f"🎯 Лучший выигрыш: {stats['win_amount']:,} монет"
                if stats['win_rank']:
                    reply_text += f" (место #{stats['win_rank']})"
                reply_text += "\n"
            else:
                reply_text += "🎯 Сегодня еще не было выигрышей\n"

            if stats['loss_amount'] > 0:
                reply_text += f"💸 Максимальный проигрыш: {stats['loss_amount']:,} монет"
                if stats['loss_rank']:
                    reply_text += f" (место #{stats['loss_rank']})"
                reply_text += "\n"

            await message.reply(reply_text, parse_mode=types.ParseMode.HTML)

        except Exception as e:
            self.logger.error(f"Error in show_user_stats: {e}")
            await message.reply("❌ Ошибка при получении статистики.")

    # =============================================
    # 🎯 ОБРАБОТЧИК КОМАНДЫ ТОП
    # =============================================

    async def handle_top_command(self, message: types.Message):
        """Обработчик всех вариантов команды топ"""
        await self.top_handlers.show_rich_top(message)


def register_record_handlers(dp: Dispatcher, record_service: RecordService = None):
    """Регистрация всех обработчиков записей"""
    global _AUTO_TOP_MW_INSTALLED

    handler = RecordCommands()

    # Если передан record_service, используем его
    if record_service:
        handler.service = record_service

    # ✅ КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ:
    # подключаем middleware, который автоматически добавляет пользователя в UserChat,
    # чтобы он попадал в "топ богатеев" после любой активности (в т.ч. команды "б").
    if not _AUTO_TOP_MW_INSTALLED:
        try:
            dp.middleware.setup(AutoTopMiddleware(throttle_seconds=3600))
            _AUTO_TOP_MW_INSTALLED = True
            handler.logger.info("✅ AutoTopMiddleware подключен")
        except Exception as e:
            handler.logger.error(f"❌ Не удалось подключить AutoTopMiddleware: {e}")

    # 🔥 РЕКОРДЫ ДНЯ (доступны всем)
    dp.register_message_handler(
        handler.check_daily_record,
        commands=['record', 'рекорд_дня', 'рекорддня', 'рекорд'],
        commands_prefix='!/'
    )
    dp.register_message_handler(
        handler.check_daily_record,
        lambda m: m.text and re.match(r'^(рекорд(\s*дня)?|record)$', m.text.lower().strip())
    )

    # 🏅 ОБРАБОТЧИКИ КОМАНДЫ ТОП
    dp.register_message_handler(
        handler.handle_top_command,
        commands=['top', 'топ'],
        commands_prefix='!/'
    )
    dp.register_message_handler(
        handler.handle_top_command,
        lambda m: m.text and re.match(r'^(топ|top)\s*\d*$', m.text.lower().strip())
    )

    # 💰 ПРЯМОЙ ТОП БОГАТЕЕВ
    dp.register_message_handler(
        handler.top_handlers.show_rich_top_direct,
        commands=['богатеи', 'rich'],
        commands_prefix='!/'
    )
    dp.register_message_handler(
        handler.top_handlers.show_rich_top_direct,
        lambda m: m.text and m.text.lower().strip() in ['богатеи', 'топ богатеев', 'топ богачей', 'rich top']
    )

    # 📊 ПОЗИЦИЯ ПОЛЬЗОВАТЕЛЯ В ТОПЕ
    dp.register_message_handler(
        handler.show_my_position,
        lambda m: m.text and m.text.lower().strip() in ['позиция', 'мой топ', 'my position', 'position', 'место']
    )

    # ⚡ БЫСТРЫЙ ТОП ЧАТА
    dp.register_message_handler(
        handler.handle_quick_top,
        lambda m: m.text and m.text.lower().strip() in ['быстрый топ', 'quick top', 'топ чата', 'чат топ']
    )

    # 👑 АДМИНСКИЕ КОМАНДЫ СТАТИСТИЧЕСКИХ ТОПОВ
    dp.register_message_handler(
        handler.top_handlers.show_stats_top,
        lambda m: m.text and any(word in m.text.lower() for word in [
            'макс выигрыш', 'макс проигрыш', 'макс ставка'
        ])
    )

    # 🔘 CALLBACK'И ДЛЯ ИНТЕРАКТИВНЫХ КНОПОК
    dp.register_callback_query_handler(
        handler.top_handlers.handle_top_callback,
        lambda c: c.data.startswith('top_')
    )

    handler.logger.info("✅ Обработчики записей зарегистрированы")
