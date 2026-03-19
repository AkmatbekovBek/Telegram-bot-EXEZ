import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Command

from database import models

logger = logging.getLogger(__name__)


class ChatHandlers:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def handle_bot_added_to_chat(self, message: types.Message):
        """Обработчик добавления бота в чат"""
        try:
            from database import get_db
            from database.crud import ChatStatsRepository

            # Проверяем, добавили ли именно бота
            for new_member in message.new_chat_members:
                if new_member.id == message.bot.id:
                    chat_id = message.chat.id
                    chat_title = message.chat.title
                    chat_type = message.chat.type

                    db = next(get_db())
                    try:
                        # Сохраняем чат в базу
                        ChatStatsRepository.add_chat(db, chat_id, chat_title, chat_type)
                        logger.info(f"✅ Бот добавлен в чат: {chat_title} (ID: {chat_id}, тип: {chat_type})")

                        # Приветственное сообщение
                        welcome_text = (
                            "👋 Всем привет!\n"
                            "Я бот с игровыми механиками и системой монет 🎮💎\n"
                            "🧩 Что доступно:\n"
                            "• /start — создать профиль\n"
                            "• /roulette - игра в рулетку\n"
                            "• /shop — подарки и бонусы\n"
                            "• /top — рейтинг участников чата\n"
                            "• /record — рекорды дня\n\n"
                            "💰 У каждого участника есть личный баланс\n"
                            "🎁 Делитесь подарками и повышайте свой рейтинг"
                        )

                        await message.answer(welcome_text)

                    except Exception as e:
                        logger.error(f"❌ Ошибка сохранения чата: {e}")
                    finally:
                        db.close()
                    break

        except Exception as e:
            logger.error(f"❌ Ошибка обработки добавления в чат: {e}")

    async def handle_chat_migration(self, message: types.Message):
        """Обработчик миграции чата (из группы в супергруппу)"""
        try:
            from database import get_db
            from database.crud import ChatStatsRepository

            old_chat_id = message.migrate_from_chat_id
            new_chat_id = message.chat.id

            if old_chat_id:
                db = next(get_db())
                try:
                    # Обновляем chat_id в базе данных
                    from database.models import UserChat, DailyRecord

                    # Обновляем UserChat
                    db.query(UserChat).filter(UserChat.chat_id == old_chat_id).update(
                        {"chat_id": new_chat_id}
                    )

                    # Обновляем DailyRecord
                    db.query(DailyRecord).filter(DailyRecord.chat_id == old_chat_id).update(
                        {"chat_id": new_chat_id}
                    )

                    # Обновляем запись чата
                    chat = db.query(models.Chat).filter(models.Chat.chat_id == old_chat_id).first()
                    if chat:
                        chat.chat_id = new_chat_id
                        chat.chat_type = "supergroup"

                    db.commit()
                    self.logger.info(f"✅ Чат мигрирован: {old_chat_id} -> {new_chat_id}")

                    # Уведомляем о успешной миграции
                    await message.answer(
                        "✅ Чат успешно обновлен! Все данные перенесены в новую супергруппу."
                    )

                except Exception as e:
                    db.rollback()
                    self.logger.error(f"❌ Ошибка миграции чата: {e}")
                    # Можно добавить уведомление об ошибке
                    await message.answer(
                        "⚠️ Произошла ошибка при миграции данных. Пожалуйста, перезапустите бота командой /start"
                    )
                finally:
                    db.close()

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки миграции чата: {e}")


def register_chat_handlers(dp: Dispatcher):
    """Регистрирует обработчики чатов"""
    handler = ChatHandlers()

    # Обработчик добавления бота в чат
    dp.register_message_handler(
        handler.handle_bot_added_to_chat,
        content_types=types.ContentType.NEW_CHAT_MEMBERS
    )

    # Обработчик миграции чата
    dp.register_message_handler(
        handler.handle_chat_migration,
        content_types=types.ContentType.MIGRATE_FROM_CHAT_ID
    )

    logger.info("✅ Chat handlers registered")