# middlewares/bot_ban_middleware.py
import logging
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler


class BotBanMiddleware(BaseMiddleware):
    def __init__(self, mute_ban_manager):
        super().__init__()
        self.mute_ban_manager = mute_ban_manager
        self.logger = logging.getLogger(__name__)
        self.recently_unbanned = set()

    async def on_pre_process_message(self, message: types.Message, data: dict):
        # Пропускаем служебные сообщения (но не текстовые команды)
        user_id = message.from_user.id

        # Проверяем, не был ли пользователь только что разбанен
        if user_id in self.recently_unbanned:
            self.logger.info(f"Пользователь {user_id} недавно разбанен, отправляем уведомление")
            # Отправляем уведомление о разбане только в ЛС
            if message.chat.type == 'private':
                try:
                    await message.answer(
                        "✅ Ваш бан в боте закончился!\n\n"
                        "Теперь вы снова можете использовать все команды бота. "
                        "Пожалуйста, соблюдайте правила, чтобы избежать повторных ограничений."
                    )
                    self.logger.info(f"Отправлено уведомление о разбане пользователю {user_id}")
                except Exception as e:
                    self.logger.error(f"Ошибка отправки уведомления о разбане: {e}")

            # Удаляем из временного списка после отправки уведомления
            self.recently_unbanned.remove(user_id)
            return

        # Пропускаем команды от администраторов
        try:
            if await self.mute_ban_manager._is_user_admin(user_id):
                self.logger.debug(f"Пользователь {user_id} является админом, пропускаем")
                return
        except Exception as e:
            self.logger.error(f"Ошибка проверки прав администратора для {user_id}: {e}")
            # В случае ошибки продолжаем обработку

        # Проверяем, забанен ли пользователь в боте
        try:
            is_banned = await self.mute_ban_manager.check_bot_ban(user_id)
            self.logger.debug(f"Проверка бана для {user_id}: {is_banned}")

            if is_banned:
                self.logger.info(
                    f"Заблокирована команда от забаненного пользователя {user_id}: '{message.text[:50] if message.text else message.caption[:50] if message.caption else 'без текста'}'")

                # Если это ЛС с ботом - отправляем сообщение о бане
                if message.chat.type == 'private':
                    try:
                        # Получаем информацию о бане
                        ban_info = await self.mute_ban_manager.get_bot_ban_info(user_id)
                        if ban_info:
                            reason = ban_info.get('reason', 'Не указана')
                            banned_at = ban_info.get('banned_at_text', 'Неизвестно')
                            expires_at = ban_info.get('expires_at_text')

                            if expires_at:
                                response_text = (
                                    f"🚫 Вы забанены в боте!\n\n"
                                    f"📝 Причина: {reason}\n"
                                    f"🕒 Забанен: {banned_at}\n"
                                    f"⏰ Срок: до {expires_at}\n\n"
                                    f"⚠️ Вы не можете использовать команды бота до окончания бана."
                                )
                            else:
                                response_text = (
                                    f"🚫 Вы забанены в боте навсегда!\n\n"
                                    f"📝 Причина: {reason}\n"
                                    f"🕒 Забанен: {banned_at}\n\n"
                                    f"⚠️ Вы не можете использовать команды бота."
                                )
                        else:
                            response_text = "🚫 Вы забанены в боте и не можете использовать команды."

                        await message.answer(response_text)
                        self.logger.info(f"Отправлено сообщение о бане пользователю {user_id}")
                    except Exception as e:
                        self.logger.error(f"Ошибка отправки сообщения о бане пользователю {user_id}: {e}")

                # В чатах тоже отвечаем, но коротко
                elif message.text and message.text.startswith('/'):
                    try:
                        await message.answer("🚫 Вы забанены в боте и не можете использовать команды.")
                    except Exception as e:
                        self.logger.error(f"Ошибка ответа в чате: {e}")

                # Останавливаем обработку сообщения
                raise CancelHandler()

        except CancelHandler:
            # Пропускаем исключение CancelHandler
            raise
        except Exception as e:
            self.logger.error(f"Ошибка проверки бана для пользователя {user_id}: {e}")

    async def on_pre_process_callback_query(self, callback_query: types.CallbackQuery, data: dict):
        user_id = callback_query.from_user.id
        self.logger.debug(f"Проверка колбэка от пользователя {user_id}")

        # Проверяем, не был ли пользователь только что разбанен
        if user_id in self.recently_unbanned:
            # Для колбэков тоже показываем уведомление о разбане
            try:
                await callback_query.answer(
                    "✅ Ваш бан закончился! Теперь вы можете использовать функции бота.",
                    show_alert=True
                )
                self.logger.info(f"Отправлено уведомление о разбане через колбэк пользователю {user_id}")
            except Exception as e:
                self.logger.error(f"Ошибка отправки уведомления в колбэке: {e}")

            # Удаляем из временного списка
            self.recently_unbanned.remove(user_id)
            return

        # Пропускаем колбэки от администраторов
        try:
            if await self.mute_ban_manager._is_user_admin(user_id):
                self.logger.debug(f"Пользователь {user_id} является админом, пропускаем колбэк")
                return
        except Exception as e:
            self.logger.error(f"Ошибка проверки прав администратора в колбэке: {e}")

        # Проверяем, забанен ли пользователь в боте
        try:
            is_banned = await self.mute_ban_manager.check_bot_ban(user_id)
            if is_banned:
                self.logger.info(f"Заблокирован колбэк от забаненного пользователя {user_id}")

                # Для колбэков всегда показываем уведомление
                try:
                    await callback_query.answer("🚫 Вы забанены в боте и не можете использовать эту функцию.",
                                                show_alert=True)
                except Exception as e:
                    self.logger.error(f"Ошибка ответа на колбэк: {e}")

                # Останавливаем обработку колбэка
                raise CancelHandler()
        except CancelHandler:
            raise
        except Exception as e:
            self.logger.error(f"Ошибка проверки бана в колбэке: {e}")

    def add_recently_unbanned(self, user_id: int):
        """Добавляет пользователя в список недавно разбаненных"""
        self.recently_unbanned.add(user_id)
        self.logger.info(f"Добавлен пользователь {user_id} в список недавно разбаненных")