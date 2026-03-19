"""
Команды очистки базы данных для администраторов Telegram бота
"""
import asyncio
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.cleanup_commands import CleanupCommands
from database import SessionLocal
from database.crud import UserRepository
import logging

logger = logging.getLogger(__name__)


class CleanupAdminHandler:
    """Обработчик команд очистки для администраторов"""

    def __init__(self):
        self.cleanup_commands = CleanupCommands()

    async def check_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором"""
        db = SessionLocal()
        try:
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if user and user.is_admin:
                return True

            # Проверяем также константные ID администраторов
            from handlers.admin.admin_constants import ADMIN_IDS
            if user_id in ADMIN_IDS:
                return True

            return False
        finally:
            db.close()

    async def cleanup_menu(self, message: types.Message):
        """Меню команд очистки базы данных"""
        if not await self.check_admin(message.from_user.id):
            await message.answer("❌ У вас нет прав администратора")
            return

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🗑️ Полная очистка", callback_data="admin_cleanup_full"),
            InlineKeyboardButton("💰 Очистить балансы", callback_data="admin_cleanup_balances"),
            InlineKeyboardButton("📊 Очистить транзакции", callback_data="admin_cleanup_transactions"),
            InlineKeyboardButton("🎮 Очистить игровые данные", callback_data="admin_cleanup_game"),
            InlineKeyboardButton("🔄 Сбросить балансы", callback_data="admin_cleanup_reset_balances"),
            InlineKeyboardButton("📋 Статистика БД", callback_data="admin_cleanup_stats"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin_cleanup_cancel")
        )

        await message.answer(
            "🧹 <b>Команды очистки базы данных</b>\n\n"
            "⚠️ <b>Внимание!</b> Эти команды необратимо удаляют данные.\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    async def handle_cleanup_full(self, callback: types.CallbackQuery):
        """Обработчик полной очистки"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        # Создаем клавиатуру подтверждения
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ ДА, очистить всё", callback_data="admin_cleanup_full_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin_cleanup_cancel")
        )

        await callback.message.edit_text(
            "⚠️ <b>ПОЛНАЯ ОЧИСТКА ВСЕХ ДАННЫХ</b>\n\n"
            "‼️ <b>Это действие очистит:</b>\n"
            "• Всех пользователей (сбросит данные на начальные)\n"
            "• Все транзакции и переводы\n"
            "• Все игровые данные (рулетка, кражи, браки)\n"
            "• Все записи о покупках и подарках\n"
            "• Все чаты и логи\n"
            "• Все рекорды и статистику\n\n"
            "<b>Данные будут потеряны безвозвратно!</b>\n\n"
            "Вы уверены?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()

    async def handle_cleanup_full_confirm(self, callback: types.CallbackQuery):
        """Подтверждение полной очистки"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        await callback.message.edit_text(
            "🔄 <b>Начинаю полную очистку базы данных...</b>\n"
            "⏳ Это может занять некоторое время...",
            parse_mode="HTML"
        )

        try:
            # Запускаем очистку в отдельной задаче
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self.cleanup_commands.full_cleanup)

            if success:
                result_text = (
                    "✅ <b>Полная очистка завершена успешно!</b>\n\n"
                    "📊 <b>Результаты:</b>\n"
                    "• Все данные очищены\n"
                    "• Пользователи сброшены\n"
                    "• База данных восстановлена до начального состояния"
                )
            else:
                result_text = "❌ <b>Ошибка при выполнении полной очистки!</b>"

        except Exception as e:
            logger.error(f"Ошибка при полной очистке: {e}")
            result_text = f"❌ <b>Произошла ошибка:</b>\n<code>{str(e)[:100]}</code>"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_cleanup_back"))

        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    async def handle_cleanup_balances(self, callback: types.CallbackQuery):
        """Обработчик очистки балансов"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Очистить балансы", callback_data="admin_cleanup_balances_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin_cleanup_cancel")
        )

        await callback.message.edit_text(
            "💰 <b>ОЧИСТКА БАЛАНСОВ И СТАТИСТИКИ</b>\n\n"
            "📊 <b>Будет очищено:</b>\n"
            "• Все транзакции и переводы\n"
            "• Балансы всех пользователей (сбросятся на 5000)\n"
            "• Вся игровая статистика (выигрыши/проигрыши)\n"
            "• Все ежедневные рекорды\n\n"
            "👤 <b>Сохранено:</b>\n"
            "• Пользователи и их настройки\n"
            "• Привилегии и покупки\n"
            "• Чаты и активность\n\n"
            "Вы уверены?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()

    async def handle_cleanup_balances_confirm(self, callback: types.CallbackQuery):
        """Подтверждение очистки балансов"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        await callback.message.edit_text(
            "🔄 <b>Начинаю очистку балансов...</b>\n"
            "⏳ Это может занять некоторое время...",
            parse_mode="HTML"
        )

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, self.cleanup_commands.cleanup_balances_only)

            if success:
                result_text = (
                    "✅ <b>Очистка балансов завершена!</b>\n\n"
                    "📊 <b>Результаты:</b>\n"
                    "• Все балансы сброшены на 5000 монет\n"
                    "• Статистика обнулена\n"
                    "• Транзакции удалены\n"
                    "• Пользователи сохранены"
                )
            else:
                result_text = "❌ <b>Ошибка при очистке балансов!</b>"

        except Exception as e:
            logger.error(f"Ошибка при очистке балансов: {e}")
            result_text = f"❌ <b>Произошла ошибка:</b>\n<code>{str(e)[:100]}</code>"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_cleanup_back"))

        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    async def handle_cleanup_transactions(self, callback: types.CallbackQuery):
        """Обработчик очистки транзакций"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Очистить историю", callback_data="admin_cleanup_transactions_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin_cleanup_cancel")
        )

        await callback.message.edit_text(
            "📊 <b>ОЧИСТКА ИСТОРИИ ТРАНЗАКЦИЙ</b>\n\n"
            "💸 <b>Будет очищено:</b>\n"
            "• Вся история переводов между пользователями\n"
            "• Все записи о лимитах переводов\n"
            "• Вся история операций с монетами\n\n"
            "👤 <b>Сохранено:</b>\n"
            "• Текущие балансы пользователей\n"
            "• Вся остальная информация\n\n"
            "Вы уверены?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()

    async def handle_cleanup_transactions_confirm(self, callback: types.CallbackQuery):
        """Подтверждение очистки транзакций"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        await callback.message.edit_text(
            "🔄 <b>Начинаю очистку истории транзакций...</b>",
            parse_mode="HTML"
        )

        try:
            loop = asyncio.get_event_loop()
            stats = await loop.run_in_executor(None, self.cleanup_commands.cleanup_transactions_only)

            if stats:
                result_text = (
                    "✅ <b>Очистка истории транзакций завершена!</b>\n\n"
                    "📊 <b>Результаты:</b>\n"
                )

                for table_name, count in stats.items():
                    result_text += f"• {table_name}: {count} записей\n"

                result_text += "\n💳 <b>Текущие балансы сохранены</b>"
            else:
                result_text = "❌ <b>Ошибка при очистке истории транзакций!</b>"

        except Exception as e:
            logger.error(f"Ошибка при очистке транзакций: {e}")
            result_text = f"❌ <b>Произошла ошибка:</b>\n<code>{str(e)[:100]}</code>"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_cleanup_back"))

        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    async def handle_cleanup_game(self, callback: types.CallbackQuery):
        """Обработчик очистки игровых данных"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("✅ Очистить игровые данные", callback_data="admin_cleanup_game_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin_cleanup_cancel")
        )

        await callback.message.edit_text(
            "🎮 <b>ОЧИСТКА ИГРОВЫХ ДАННЫХ</b>\n\n"
            "🎰 <b>Будет очищено:</b>\n"
            "• Вся история рулетки\n"
            "• Все данные о кражах и арестах\n"
            "• Все браки и разводы\n"
            "• Логи игр рулетки\n"
            "• Лимиты рулетки\n\n"
            "👤 <b>Сохранено:</b>\n"
            "• Пользователи и балансы\n"
            "• Основные транзакции\n"
            "• Привилегии и покупки\n\n"
            "Вы уверены?",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()

    async def handle_cleanup_game_confirm(self, callback: types.CallbackQuery):
        """Подтверждение очистки игровых данных"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        await callback.message.edit_text(
            "🔄 <b>Начинаю очистку игровых данных...</b>",
            parse_mode="HTML"
        )

        try:
            loop = asyncio.get_event_loop()
            stats = await loop.run_in_executor(None, self.cleanup_commands.cleanup_game_data_only)

            if stats:
                result_text = (
                    "✅ <b>Очистка игровых данных завершена!</b>\n\n"
                    "📊 <b>Результаты:</b>\n"
                )

                for table_name, count in stats.items():
                    result_text += f"• {table_name}: {count} записей\n"

                result_text += "\n🎮 <b>Игровые данные удалены</b>"
            else:
                result_text = "❌ <b>Ошибка при очистке игровых данных!</b>"

        except Exception as e:
            logger.error(f"Ошибка при очистке игровых данных: {e}")
            result_text = f"❌ <b>Произошла ошибка:</b>\n<code>{str(e)[:100]}</code>"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_cleanup_back"))

        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    async def handle_reset_balances(self, callback: types.CallbackQuery):
        """Обработчик сброса балансов на значение по умолчанию"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("🔹 5000 монет", callback_data="admin_cleanup_reset_5000"),
            InlineKeyboardButton("🔸 10000 монет", callback_data="admin_cleanup_reset_10000"),
            InlineKeyboardButton("🔶 50000 монет", callback_data="admin_cleanup_reset_50000"),
            InlineKeyboardButton("💎 100000 монет", callback_data="admin_cleanup_reset_100000"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin_cleanup_cancel")
        )

        await callback.message.edit_text(
            "🔄 <b>СБРОС БАЛАНСОВ ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
            "💰 Выберите сумму, на которую будут сброшены балансы всех пользователей:\n\n"
            "⚠️ <b>Внимание:</b>\n"
            "Это действие изменит балансы всех пользователей на выбранную сумму.",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()

    async def handle_reset_balances_confirm(self, callback: types.CallbackQuery):
        """Подтверждение сброса балансов"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        # Получаем сумму из callback_data
        amount_str = callback.data.replace("admin_cleanup_reset_", "")
        try:
            amount = int(amount_str)
        except:
            amount = 5000  # Значение по умолчанию

        await callback.message.edit_text(
            f"🔄 <b>Сбрасываю все балансы на {amount} монет...</b>",
            parse_mode="HTML"
        )

        try:
            loop = asyncio.get_event_loop()
            reset_count = await loop.run_in_executor(
                None,
                lambda: self.cleanup_commands.reset_user_balances_to_default(amount)
            )

            if reset_count > 0:
                result_text = (
                    f"✅ <b>Сброс балансов завершен!</b>\n\n"
                    f"📊 <b>Результаты:</b>\n"
                    f"• Сброшено балансов: {reset_count} пользователей\n"
                    f"• Установленная сумма: {amount} монет\n"
                    f"• Все остальные данные сохранены"
                )
            else:
                result_text = "❌ <b>Ошибка при сбросе балансов!</b>"

        except Exception as e:
            logger.error(f"Ошибка при сбросе балансов: {e}")
            result_text = f"❌ <b>Произошла ошибка:</b>\n<code>{str(e)[:100]}</code>"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_cleanup_back"))

        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    async def handle_cleanup_stats(self, callback: types.CallbackQuery):
        """Показать статистику базы данных"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        try:
            from database import SessionLocal
            from database.models import (
                TelegramUser, Transaction, RouletteTransaction,
                DailyRecord, UserPurchase, Gift, UserChat, ReferenceUser,
                RouletteGameLog, StealAttempt, Marriage, DonatePurchase
            )

            db = SessionLocal()
            try:
                stats_text = "📊 <b>СТАТИСТИКА БАЗЫ ДАННЫХ</b>\n\n"

                stats = {
                    "👤 Пользователей": TelegramUser,
                    "💸 Переводов": Transaction,
                    "🎰 Ставок в рулетке": RouletteTransaction,
                    "🏆 Рекордов дня": DailyRecord,
                    "🛒 Покупок": UserPurchase,
                    "🎁 Подарков (каталог)": Gift,
                    "💬 Пользователей в чатах": UserChat,
                    "👥 Рефералов": ReferenceUser,
                    "📊 Логов рулетки": RouletteGameLog,
                    "🦹 Попыток краж": StealAttempt,
                    "💍 Браков": Marriage,
                    "💰 Донат-покупок": DonatePurchase,
                }

                total_records = 0
                for name, model in stats.items():
                    try:
                        count = db.query(model).count()
                        total_records += count
                        stats_text += f"• {name}: {count:,}\n".replace(",", " ")
                    except:
                        stats_text += f"• {name}: ошибка\n"

                stats_text += f"\n📈 Всего записей: {total_records:,}".replace(",", " ")

                # Дополнительная статистика
                try:
                    total_coins = db.query(TelegramUser.coins).all()
                    if total_coins:
                        total = sum([coin[0] for coin in total_coins if coin[0] is not None])
                        stats_text += f"\n💰 Общая сумма монет: {total:,}".replace(",", " ")
                except:
                    pass

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            stats_text = f"❌ <b>Ошибка получения статистики:</b>\n<code>{str(e)[:100]}</code>"

        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("🔄 Обновить", callback_data="admin_cleanup_stats"))
        keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_cleanup_back"))

        await callback.message.edit_text(stats_text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    async def handle_cleanup_cancel(self, callback: types.CallbackQuery):
        """Отмена очистки"""
        await callback.message.delete()
        await callback.answer("❌ Операция отменена")

    async def handle_cleanup_back(self, callback: types.CallbackQuery):
        """Возврат в меню очистки"""
        if not await self.check_admin(callback.from_user.id):
            await callback.answer("❌ У вас нет прав", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🗑️ Полная очистка", callback_data="admin_cleanup_full"),
            InlineKeyboardButton("💰 Очистить балансы", callback_data="admin_cleanup_balances"),
            InlineKeyboardButton("📊 Очистить транзакции", callback_data="admin_cleanup_transactions"),
            InlineKeyboardButton("🎮 Очистить игровые данные", callback_data="admin_cleanup_game"),
            InlineKeyboardButton("🔄 Сбросить балансы", callback_data="admin_cleanup_reset_balances"),
            InlineKeyboardButton("📋 Статистика БД", callback_data="admin_cleanup_stats"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin_cleanup_cancel")
        )

        await callback.message.edit_text(
            "🧹 <b>Команды очистки базы данных</b>\n\n"
            "⚠️ <b>Внимание!</b> Эти команды необратимо удаляют данные.\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()


def register_cleanup_handlers(dp: Dispatcher):
    """Регистрирует обработчики команд очистки"""
    handler = CleanupAdminHandler()

    # Команды
    dp.register_message_handler(
        handler.cleanup_menu,
        commands=['очистить', 'cleanup', 'db_cleanup', 'очистка']
    )

    dp.register_message_handler(
        handler.cleanup_menu,
        lambda m: m.text and m.text.lower() in [
            'очистить базу', 'очистка базы', 'clean database',
            'управление базой', 'db management'
        ]
    )

    # Callback обработчики
    callback_handlers = [
        (handler.handle_cleanup_full, "admin_cleanup_full"),
        (handler.handle_cleanup_full_confirm, "admin_cleanup_full_confirm"),
        (handler.handle_cleanup_balances, "admin_cleanup_balances"),
        (handler.handle_cleanup_balances_confirm, "admin_cleanup_balances_confirm"),
        (handler.handle_cleanup_transactions, "admin_cleanup_transactions"),
        (handler.handle_cleanup_transactions_confirm, "admin_cleanup_transactions_confirm"),
        (handler.handle_cleanup_game, "admin_cleanup_game"),
        (handler.handle_cleanup_game_confirm, "admin_cleanup_game_confirm"),
        (handler.handle_reset_balances, "admin_cleanup_reset_balances"),
        (handler.handle_reset_balances_confirm, lambda c: c.data.startswith("admin_cleanup_reset_")),
        (handler.handle_cleanup_stats, "admin_cleanup_stats"),
        (handler.handle_cleanup_cancel, "admin_cleanup_cancel"),
        (handler.handle_cleanup_back, "admin_cleanup_back"),
    ]

    for handler_func, filter_data in callback_handlers:
        if callable(filter_data):
            dp.register_callback_query_handler(handler_func, filter_data)
        else:
            dp.register_callback_query_handler(
                handler_func,
                lambda c, data=filter_data: c.data == data
            )

    logger.info("✅ Обработчики команд очистки зарегистрированы")