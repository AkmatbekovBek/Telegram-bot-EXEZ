# middlewares/throttling.py
from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.utils.exceptions import Throttled
import asyncio


class ThrottlingMiddleware(BaseMiddleware):
    """
    Мидлварь для анти-спама с настраиваемым списком команд
    """

    def __init__(self, throttled_commands: list = None, limit=3, key_prefix='antiflood_'):
        self.rate_limit = limit
        self.prefix = key_prefix
        # Команды, на которые действует антифлуд (без слеша)
        self.throttled_commands = throttled_commands or []
        super(ThrottlingMiddleware, self).__init__()

    async def on_process_message(self, message: Message, data: dict):
        # Проверяем, является ли сообщение командой из списка
        if not await self.is_throttled_command(message):
            return

        # Проверяем, является ли пользователь админом (исключаем из антифлуда)
        if await self.is_admin(message):
            return

        dispatcher = Dispatcher.get_current()

        try:
            await dispatcher.throttle(
                f"{self.prefix}_{message.from_user.id}",
                rate=self.rate_limit
            )
        except Throttled as throttled:
            await self.message_throttled(message, throttled)
            raise CancelHandler()

    async def is_throttled_command(self, message: Message) -> bool:
        """
        Проверяем, является ли сообщение командой из списка throttled_commands
        """
        if not message.text:
            return False

        # Проверяем команды с слешем (/command)
        if message.text.startswith('/'):
            if not message.entities:
                return False

            for entity in message.entities:
                if entity.type == "bot_command":
                    command_text = message.text[entity.offset:entity.offset + entity.length]
                    command_name = command_text[1:].split('@')[0]  # Убираем / и username бота

                    # Проверяем, есть ли команда в списке
                    if command_name in self.throttled_commands:
                        return True

                    # Также проверяем команды с параметрами
                    base_command = command_name.split()[0] if ' ' in command_name else command_name
                    if base_command in self.throttled_commands:
                        return True

        # Проверяем текстовые команды без слеша
        else:
            # Берем первое слово из сообщения
            first_word = message.text.split()[0].lower() if message.text else ""
            return first_word in self.throttled_commands

        return False

    async def message_throttled(self, message: Message, throttled: Throttled):
        """
        Отправляем сообщение о необходимости подождать и удаляем его через 3 секунды
        """
        delta = throttled.rate - throttled.delta

        # Отправляем сообщение только если это первое превышение
        if throttled.exceeded_count <= 2:
            # Получаем имя пользователя или используем "Пользователь"
            user_name = message.from_user.first_name or "Пользователь"

            # Отправляем обычное сообщение вместо ответа
            warning_message = await message.answer(
                f"{user_name}, вы не можете использовать бота ещё {delta:.1f} секунды"
            )

            # Удаляем только предупреждающее сообщение через 3 секунды
            await asyncio.sleep(3)
            try:
                await warning_message.delete()
            except Exception:
                # Игнорируем ошибки удаления
                pass

    async def is_admin(self, message: Message) -> bool:
        """
        Проверяем, является ли пользователь администратором
        """
        # Список ID администраторов (замените на ваши реальные ID)
        admin_ids = [1054684037]  # Пример ID админа

        return message.from_user.id in admin_ids


def setup_throttling(dp: Dispatcher, throttled_commands: list = None, limit: int = 3):
    """
    Установка мидлвари для антифлуда с настраиваемым списком команд
    """
    if throttled_commands is None:
        throttled_commands = ['start', 'help', 'menu']

    throttling_middleware = ThrottlingMiddleware(
        throttled_commands=throttled_commands,
        limit=limit
    )
    dp.middleware.setup(throttling_middleware)

    commands_str = ', '.join([f'/{cmd}' if len(cmd) > 1 else cmd for cmd in throttled_commands])
    print(f"✅ Антифлуд активирован для команд: {commands_str} (лимит: {limit}с)")

    return throttling_middleware