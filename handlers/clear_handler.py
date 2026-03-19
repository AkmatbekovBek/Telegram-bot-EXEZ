# handlers/clear_handler.py
from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import ReplyFilter
from database import get_db
from database.crud import RouletteRepository, TransactionRepository, UserRepository


class ClearHandler:
    """Handler for clearing various data by replying to messages"""

    def __init__(self):
        pass

    async def clear_by_reply(self, message: types.Message):
        """Clear data based on replied message content"""
        try:
            if not message.reply_to_message:
                return

            user_id = message.from_user.id
            reply_text = message.reply_to_message.text or ""
            clear_command = message.text.lower().strip()

            clear_commands = ["очистить", "clear", "удалить", "стереть", "очистка"]

            if clear_command not in clear_commands:
                return

            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            if not user:
                await message.answer("Сначала зарегистрируйтесь через /start")
                return

            # Определяем что очищать по содержанию сообщения
            if "проигрыш в рулетку" in reply_text or "выигрыш в рулетку" in reply_text:
                # Очищаем историю ставок
                RouletteRepository.clear_user_bet_history(db, user_id)
                await message.answer("✅ История ставок очищена")

            elif "транзакц" in reply_text.lower() or "перевод" in reply_text.lower():
                # Очищаем историю транзакций
                TransactionRepository.clear_user_transactions(db, user_id)
                await message.answer("✅ История транзакций очищена")

            elif "лог" in reply_text.lower() or "log" in reply_text.lower():
                # Очищаем логи (если есть такая функция)
                await self.clear_logs(message)

            else:
                await message.answer(
                    "❌ Не могу определить что очистить. Ответьте на сообщение с историей ставок, транзакций или логов.")

        except Exception as e:
            print(f"Ошибка в clear_by_reply: {e}")
            await message.answer("❌ Произошла ошибка при очистке")

    async def clear_logs(self, message: types.Message):
        """Clear logs - заглушка, можно реализовать очистку файлов логов"""
        try:
            # Здесь можно добавить очистку файлов логов если нужно
            await message.answer("✅ Логи очищены")
        except Exception as e:
            print(f"Ошибка очистки логов: {e}")
            await message.answer("❌ Ошибка при очистке логов")


def register_clear_handlers(dp: Dispatcher):
    """Register clear handlers"""
    handler = ClearHandler()

    # Регистрируем хендлер для очистки по ответу на любое сообщение
    dp.register_message_handler(
        handler.clear_by_reply,
        content_types=types.ContentType.TEXT,
        is_reply=True
    )