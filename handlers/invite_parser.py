# handlers/invite_parser.py
import logging
from aiogram import types, Dispatcher
from database import get_db
from database.crud import GroupInviteRepository

logger = logging.getLogger(__name__)


class InviteParserHandler:
    """Обработчик для анализа приглашений"""

    async def handle_start_with_invite(self, message: types.Message):
        """Обработка команды /start с параметром приглашения"""
        try:
            # Проверяем, что команда отправлена в личном чате
            if message.chat.type != types.ChatType.PRIVATE:
                return

            command = message.get_full_command()
            if len(command) > 1 and command[1].startswith('invite_'):
                # Извлекаем ID пригласившего из параметра
                payload = command[1]
                try:
                    inviter_id = int(payload.split('_')[1])

                    # Проверяем, что ID валидный
                    if inviter_id <= 0:
                        return

                    db = next(get_db())

                    # Сохраняем приглашение во временное хранилище
                    # (chat_id = 0 означает, что пользователь еще не вступил в группу)
                    GroupInviteRepository.add_invite(
                        db=db,
                        inviter_id=inviter_id,
                        invited_id=message.from_user.id,
                        chat_id=0  # Будет обновлено при вступлении в группу
                    )

                    # Сохраняем ID пригласившего для последующего использования
                    # в user_data или отдельной таблице
                    from aiogram.dispatcher import FSMContext
                    from aiogram.dispatcher.storage import FSMContextProxy

                    # Отправляем инструкцию
                    await message.reply(
                        f"🚪 Дверь открыта по приглашению. {message.from_user.first_name} Добро пожаловать в чат 💬"
                    )

                    db.close()

                except (ValueError, IndexError, Exception) as e:
                    logger.error(f"❌ Ошибка обработки invite ссылки: {e}")
                    return

        except Exception as e:
            logger.error(f"❌ Ошибка обработки приглашения: {e}")


def register_invite_parser_handlers(dp: Dispatcher):
    """Регистрация обработчиков приглашений"""
    handler = InviteParserHandler()

    # Обработка команды /start с параметром (только в личных сообщениях)
    dp.register_message_handler(handler.handle_start_with_invite, commands=['start'])

    logger.info("✅ InviteParserHandler зарегистрирован")