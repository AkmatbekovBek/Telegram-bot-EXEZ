# handlers/history_service.py
from aiogram import types, Dispatcher
from database import get_db
from handlers.history.merge_handler import HistoryMergeHandler


class HistoryHandler:
    """Главный обработчик истории (тонкая оболочка)"""

    def __init__(self):
        self.merge_handler = HistoryMergeHandler()

    async def show_complete_history(self, message: types.Message):
        """Показывает полную историю операций"""
        try:
            user_id = message.from_user.id

            # Проверяем, зарегистрирован ли пользователь
            db = next(get_db())
            from database.crud import UserRepository
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await message.answer("Сначала зарегистрируйтесь через /start")
                return

            # Получаем отформатированную историю
            history_text = self.merge_handler.get_formatted_history(db, user_id, limit=12)

            # Отправляем сообщение
            await message.answer(history_text)

        except Exception as e:
            print(f" Ошибка при получении истории: {e}")
            await message.answer("Произошла ошибка при получении истории")


def register_history_handlers(dp: Dispatcher):
    """Регистрирует обработчики истории"""
    handler = HistoryHandler()

    dp.register_message_handler(
        handler.show_complete_history,
        lambda m: m.text and m.text.lower().strip() in ["история", "history", "ист", "полная история",
                                                        "история операций"]
    )