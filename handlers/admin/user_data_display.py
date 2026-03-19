# handlers/admin/user_data_display.py

import logging
from datetime import datetime

import pytz
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.utils.markdown import escape_md
from database import get_db, models
from database.crud import UserRepository, TransactionRepository, ShopRepository
from handlers.admin.admin_helpers import check_admin_async, format_number
from handlers.admin.user_info_states import UserInfoStates
from handlers.history.merge_handler import HistoryMergeHandler
from handlers.admin.mute_ban import mute_ban_manager

logger = logging.getLogger(__name__)


class UserDataDisplay:
    """Обработчик информации о пользователях"""

    def __init__(self):
        self.logger = logger
        self.timezone = pytz.UTC
        self.history_merge_handler = HistoryMergeHandler()

    def _get_user_max_loss(self, db, user_id: int):
        """Получает максимальный проигрыш пользователя"""
        try:
            from sqlalchemy import func
            from database import models

            max_loss_result = db.query(
                func.min(models.RouletteTransaction.profit)
            ).filter(
                models.RouletteTransaction.user_id == user_id
            ).scalar()

            if max_loss_result and max_loss_result < 0:
                return abs(max_loss_result)
            return 0
        except Exception as e:
            self.logger.error(f"Ошибка получения max loss: {e}")
            return 0

    async def show_user_info(self, message: types.Message):
        """Показывает информацию о пользователе по ID"""
        if not await check_admin_async(message):
            return

        try:
            command_text = message.text.strip()

            if command_text.startswith('/profile '):
                potential_id = command_text[9:].strip()

                if ' ' in potential_id:
                    potential_id = potential_id.split()[0]

                if not potential_id.isdigit():
                    # ВЫЗОВИТЕ С await
                    await message.answer(await self._show_help_message(message), parse_mode="Markdown")
                    return

                user_id = int(potential_id)

                if user_id <= 0 or user_id > 9223372036854775807:
                    await message.answer("⚠️ Неверный ID пользователя")
                    return

                await self._display_user_info(message, user_id)
            else:
                # ВЫЗОВИТЕ С await
                await message.answer(await self._show_help_message(message), parse_mode="Markdown")

        except ValueError:
            await message.answer("⚠️ ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Ошибка в show_user_info: {e}")
            await message.answer("⚠️ Ошибка получения информации")

    def _show_help_message(self, message: types.Message):
        """Показывает справку по использованию"""
        help_text = (
            "🔍 **ПРОСМОТР ИНФОРМАЦИИ**\n\n"
            "**Команды:**\n"
            "`/profile 123456789` - где 123456789 ID пользователя\n\n"
            "**Через ответ на сообщение:**\n"
            "1. Ответьте на сообщение пользователя\n"
            "2. Отправьте `/profile`\n\n"
            "**Примеры:**\n"
            "• `/profile 123456789`\n"
            "• `/profile 987654321`\n"
            "• Ответ на сообщение + `/profile`\n\n"
            "👮‍♂️ *Только для администраторов*"
        )
        message.answer(help_text, parse_mode="Markdown")

    async def show_user_info_reply(self, message: types.Message):
        """Показывает информацию о пользователе из reply сообщения"""
        if not await check_admin_async(message):
            return

        try:
            if message.text and message.text.strip().lower() == '/profile':
                if message.reply_to_message and message.reply_to_message.from_user:
                    user_id = message.reply_to_message.from_user.id
                    await self._display_user_info(message, user_id)
                else:
                    await message.answer(
                        "**Использование команды:**\n\n"
                        "1. Найдите сообщение пользователя\n"
                        "2. Ответьте на него\n"
                        "3. Отправьте `/profile`\n\n"
                        "Или используйте прямую ссылку:\n"
                        "`/profile 123456789`",
                        parse_mode="Markdown"
                    )

        except Exception as e:
            self.logger.error(f"Ошибка в show_user_info_reply: {e}")
            await message.answer("⚠️ Ошибка получения информации")

    async def _display_user_info(self, message: types.Message, user_id: int):
        """Формирует и отображает информацию о пользователе"""
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await message.answer(f"⚠️ Пользователь с ID {user_id} не найден")
                db.close()
                return

            max_loss = self._get_user_max_loss(db, user_id)

            info_text = (
                f"👤 **ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ**\n\n"
                f"**ID:** `{user_id}`\n"
                f"**Имя:** {escape_md(str(self._get_user_display_name(user)))}\n\n"
                f"💰 **Баланс:** {format_number(user.coins)} монет\n"
                f"✅ **Выиграно всего:** {format_number(user.win_coins or 0)} монет\n"
                f"❌ **Проиграно всего:** {format_number(user.defeat_coins or 0)} монет\n"
                f"🎯 **Максимальная ставка:** {format_number(user.max_bet or 0)} монет\n"
                f"📉 **Максимальный проигрыш:** {format_number(max_loss)} монет\n"
                f"📈 **Максимальный выигрыш:** {format_number(user.max_win_coins or 0)} монет\n"
            )

            try:
                is_banned = mute_ban_manager.bot_ban_manager.is_user_bot_banned(user_id)
                if is_banned:
                    info_text += f"\n🚫 **Статус:** Забанен в боте"
            except Exception as e:
                self.logger.warning(f"Не удалось проверить бан: {e}")

            if hasattr(user, 'created_at') and user.created_at:
                info_text += f"\n📅 **Зарегистрирован:** {user.created_at.strftime('%d.%m.%Y %H:%M')}"

            keyboard = self._create_user_info_keyboard(user_id)

            await message.answer(info_text, parse_mode="Markdown", reply_markup=keyboard)
            db.close()

        except Exception as e:
            self.logger.error(f"Ошибка в _display_user_info: {e}")
            await message.answer("⚠️ Ошибка формирования информации")
            try:
                db.close()
            except:
                pass

    def _get_user_display_name(self, user) -> str:
        """Возвращает отображаемое имя пользователя"""
        if user.username:
            return f"@{user.username}"
        elif user.first_name:
            return user.first_name
        else:
            return f"Пользователь {user.telegram_id}"

    def _create_user_info_keyboard(self, user_id: int) -> types.InlineKeyboardMarkup:
        """Создает клавиатуру с действиями для пользователя"""
        keyboard = types.InlineKeyboardMarkup(row_width=3)

        # Первый ряд - 3 кнопки
        keyboard.row(
            types.InlineKeyboardButton("🔄 Сбросить", callback_data=f"user_reset_{user_id}"),
            types.InlineKeyboardButton("🚫 Забанить", callback_data=f"user_ban_{user_id}"),
            types.InlineKeyboardButton("✅ Разбанить", callback_data=f"user_unban_{user_id}")
        )

        # Второй ряд - 2 кнопки
        keyboard.row(
            types.InlineKeyboardButton("🔓 Снять лимит", callback_data=f"user_unlimit_{user_id}"),
            types.InlineKeyboardButton("🔒 Установить лимит", callback_data=f"user_limit_{user_id}")
        )

        # Третий ряд - 1 кнопка
        keyboard.add(
            types.InlineKeyboardButton("📋 История операций", callback_data=f"user_history_{user_id}")
        )

        return keyboard

    async def handle_reset_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Сбросить"""
        try:
            user_id = int(callback.data.split('_')[-1])

            keyboard = types.InlineKeyboardMarkup(row_width=2)

            keyboard.row(
                types.InlineKeyboardButton("💰 Баланс", callback_data=f"reset_balance_{user_id}"),
                types.InlineKeyboardButton("✅ Выигрыши", callback_data=f"reset_wins_{user_id}")
            )

            keyboard.row(
                types.InlineKeyboardButton("❌ Проигрыши", callback_data=f"reset_losses_{user_id}"),
                types.InlineKeyboardButton("🎯 Макс ставка", callback_data=f"reset_maxbet_{user_id}")
            )

            keyboard.row(
                types.InlineKeyboardButton("📉 Макс проигрыш", callback_data=f"reset_maxloss_{user_id}"),
                types.InlineKeyboardButton("📈 Макс выигрыш", callback_data=f"reset_maxwin_{user_id}")
            )

            keyboard.add(
                types.InlineKeyboardButton("🗑️ Всё сразу", callback_data=f"reset_all_{user_id}")
            )

            keyboard.add(
                types.InlineKeyboardButton("⬅️ Назад", callback_data=f"user_back_{user_id}")
            )

            await callback.message.edit_text(
                f"🔄 **СБРОС ДАННЫХ ПОЛЬЗОВАТЕЛЯ**\n\n"
                f"👤 **Пользователь:** `{user_id}`\n\n"
                f"⚠️ **Выберите что сбросить:**\n"
                f"• `💰 Баланс` - установит баланс в 0\n"
                f"• `✅ Выигрыши` - обнулит счетчик выигрышей\n"
                f"• `❌ Проигрыши` - обнулит счетчик проигрышей\n"
                f"• `🎯 Макс ставка` - обнулит максимальную ставку\n"
                f"• `📉 Макс проигрыш` - обнулит максимальный проигрыш\n"
                f"• `📈 Макс выигрыш` - обнулит максимальный выигрыш\n\n"
                f"_После выбора потребуется подтверждение_",
                parse_mode="Markdown",
                reply_markup=keyboard
            )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в handle_reset_button: {e}")
            await callback.answer("⚠️ Ошибка обработки кнопки")

    async def handle_reset_confirm(self, callback: types.CallbackQuery):
        """Подтверждение сброса данных"""
        try:
            data_parts = callback.data.split('_')
            reset_type = data_parts[1]
            user_id = int(data_parts[-1])

            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await callback.answer("⚠️ Пользователь не найден", show_alert=True)
                db.close()
                return

            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton("✅ Да, сбросить", callback_data=f"confirm_reset_{reset_type}_{user_id}"),
                types.InlineKeyboardButton("❌ Нет, отмена", callback_data=f"user_reset_{user_id}")
            )

            reset_names = {
                'balance': 'баланс',
                'wins': 'выигрыши',
                'losses': 'проигрыши',
                'maxbet': 'максимальную ставку',
                'maxloss': 'максимальный проигрыш',
                'maxwin': 'максимальный выигрыш',
                'all': 'все данные'
            }

            await callback.message.edit_text(
                f"⚠️ **ПОДТВЕРЖДЕНИЕ СБРОСА**\n\n"
                f"👤 **Пользователь:** {self._get_user_display_name(user)} (`{user_id}`)\n"
                f"📛 **Сбросить:** **{reset_names.get(reset_type, reset_type)}**\n\n"
                f"❓ **Вы уверены, что хотите сбросить эти данные?**\n\n"
                f"_Это действие нельзя отменить!_",
                parse_mode="Markdown",
                reply_markup=keyboard
            )

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в handle_reset_confirm: {e}")
            await callback.answer("⚠️ Ошибка подтверждения")

    async def execute_reset(self, callback: types.CallbackQuery):
        """Выполняет сброс данных"""
        try:
            data_parts = callback.data.split('_')
            reset_type = data_parts[2]
            user_id = int(data_parts[3])

            db = next(get_db())

            try:
                if reset_type == 'balance':
                    UserRepository.update_user_balance(db, user_id, 0)
                    TransactionRepository.create_transaction(
                        db=db,
                        from_user_id=user_id,
                        to_user_id=None,
                        amount=0,
                        description="админ сброс баланса"
                    )

                elif reset_type == 'wins':
                    # Обновляем только win_coins
                    UserRepository.update_user_stats(db, user_id, win_coins=0)

                elif reset_type == 'losses':
                    # Обновляем только defeat_coins
                    UserRepository.update_user_stats(db, user_id, defeat_coins=0)

                elif reset_type == 'maxbet':
                    # Обновляем только max_bet
                    UserRepository.update_user_stats(db, user_id, max_bet=0)

                elif reset_type == 'maxloss':
                    # Для максимального проигрыша ничего не делаем, так как это вычисляемое значение
                    pass

                elif reset_type == 'maxwin':
                    # Обновляем только max_win_coins
                    UserRepository.update_user_stats(db, user_id, max_win_coins=0)

                elif reset_type == 'all':
                    # Сброс всех полей
                    UserRepository.update_user_balance(db, user_id, 0)
                    UserRepository.update_user_stats(
                        db, user_id,
                        win_coins=0,
                        defeat_coins=0,
                        max_win_coins=0,
                        max_bet=0
                    )
                    # Для min_win_coins, если нужно
                    if hasattr(models.TelegramUser, 'min_win_coins'):
                        UserRepository.update_user_stats(db, user_id, min_win_coins=0)

                    TransactionRepository.create_transaction(
                        db=db,
                        from_user_id=user_id,
                        to_user_id=None,
                        amount=0,
                        description="админ полный сброс"
                    )

                db.commit()

                admin_id = callback.from_user.id
                self.logger.info(f"Админ {admin_id} сбросил {reset_type} для пользователя {user_id}")

                await callback.message.edit_text(
                    f"✅ **ДАННЫЕ УСПЕШНО СБРОШЕНЫ!**\n\n"
                    f"👤 **Пользователь:** `{user_id}`\n"
                    f"📛 **Тип сброса:** {reset_type}\n"
                    f"👮‍♂️ **Администратор:** {callback.from_user.first_name}\n\n"
                    f"_Действие выполнено успешно_",
                    parse_mode="Markdown"
                )

            except Exception as db_error:
                db.rollback()
                self.logger.error(f"Ошибка БД в execute_reset: {db_error}")
                await callback.message.edit_text(
                    "❌ **ОШИБКА БАЗЫ ДАННЫХ!**\n\n"
                    "Не удалось сбросить данные. Попробуйте позже.",
                    parse_mode="Markdown"
                )

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в execute_reset: {e}")
            await callback.answer("⚠️ Ошибка выполнения сброса")

    async def handle_ban_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Забанить"""
        try:
            user_id = int(callback.data.split('_')[-1])

            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await callback.answer("⚠️ Пользователь не найден", show_alert=True)
                db.close()
                return

            is_banned = mute_ban_manager.bot_ban_manager.is_user_bot_banned(user_id)

            if is_banned:
                await callback.answer("ℹ️ Пользователь уже забанен", show_alert=True)
                db.close()
                return

            await callback.message.edit_text(
                f"🚫 **ЗАБАНИТЬ ПОЛЬЗОВАТЕЛЯ В БОТЕ**\n\n"
                f"👤 **Пользователь:** {self._get_user_display_name(user)} (`{user_id}`)\n\n"
                f"📝 **Введите причину бана:**\n"
                f"• Причина будет отправлена пользователю\n"
                f"• Можно использовать обычный текст\n"
                f"• Нажмите /cancel для отмены\n\n"
                f"_Пользователь будет заблокирован в боте до снятия бана_",
                parse_mode="Markdown"
            )

            state = Dispatcher.get_current().current_state()
            await state.update_data(ban_user_id=user_id)

            await UserInfoStates.waiting_for_ban_reason.set()

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в handle_ban_button: {e}")
            await callback.answer("⚠️ Ошибка обработки бана")

    async def handle_unban_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Разбанить"""
        try:
            user_id = int(callback.data.split('_')[-1])

            is_banned = mute_ban_manager.bot_ban_manager.is_user_bot_banned(user_id)

            if not is_banned:
                await callback.answer("ℹ️ Пользователь не забанен", show_alert=True)
                return

            success = await mute_ban_manager.unban_in_bot(user_id)

            if success:
                try:
                    await callback.bot.send_message(
                        chat_id=user_id,
                        text="✅ Вы разбанены в боте. Теперь вы можете пользоваться и играть в боте."
                    )
                except:
                    pass

                await callback.message.edit_text(
                    f"✅ **ПОЛЬЗОВАТЕЛЬ РАЗБАНЕН В БОТЕ!**\n\n"
                    f"👤 **ID:** `{user_id}`\n"
                    f"👮‍♂️ **Администратор:** {callback.from_user.first_name}\n\n"
                    f"_Пользователь получил уведомление о разбане_",
                    parse_mode="Markdown"
                )

                admin_id = callback.from_user.id
                self.logger.info(f"Админ {admin_id} разбанил пользователя {user_id} в боте")
            else:
                await callback.message.edit_text(
                    "❌ **ОШИБКА ПРИ РАЗБАНЕ В БОТЕ!**\n\n"
                    "Не удалось разбанить пользователя. Попробуйте позже.",
                    parse_mode="Markdown"
                )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в handle_unban_button: {e}")
            await callback.answer("⚠️ Ошибка разбана")

    async def handle_unlimit_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Снять лимит"""
        try:
            user_id = int(callback.data.split('_')[-1])

            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await callback.answer("⚠️ Пользователь не найден", show_alert=True)
                db.close()
                return

            user_purchases = ShopRepository.get_user_purchases(db, user_id)

            if 3 in user_purchases:
                await callback.answer("ℹ️ У пользователя уже снят лимит", show_alert=True)
                db.close()
                return

            try:
                from handlers.admin.admin_constants import PRIVILEGES, SHOP_ITEMS

                ShopRepository.add_user_purchase(
                    db,
                    user_id,
                    SHOP_ITEMS["unlimited_transfers"],
                    PRIVILEGES["unlimit"]["name"],
                    0
                )
                db.commit()

                await callback.message.edit_text(
                    f"✅ **ЛИМИТ ПЕРЕВОДОВ СНЯТ!**\n\n"
                    f"👤 **Пользователь:** {self._get_user_display_name(user)} (`{user_id}`)\n"
                    f"👮‍♂️ **Администратор:** {callback.from_user.first_name}\n\n"
                    f"_Пользователь может переводить неограниченные суммы_",
                    parse_mode="Markdown"
                )

                admin_id = callback.from_user.id
                self.logger.info(f"Админ {admin_id} снял лимит переводов пользователю {user_id}")

            except Exception as db_error:
                db.rollback()
                self.logger.error(f"Ошибка БД в handle_unlimit_button: {db_error}")
                await callback.message.edit_text(
                    "❌ **ОШИБКА БАЗЫ ДАННЫХ!**\n\n"
                    "Не удалось снять лимит. Попробуйте позже.",
                    parse_mode="Markdown"
                )

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в handle_unlimit_button: {e}")
            await callback.answer("⚠️ Ошибка при снятии лимита")

    async def handle_limit_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Установить лимит"""
        try:
            user_id = int(callback.data.split('_')[-1])

            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await callback.answer("⚠️ Пользователь не найден", show_alert=True)
                db.close()
                return

            user_purchases = ShopRepository.get_user_purchases(db, user_id)

            if 3 not in user_purchases:
                await callback.answer("ℹ️ У пользователя уже установлен лимит", show_alert=True)
                db.close()
                return

            from handlers.admin.admin_constants import SHOP_ITEMS

            try:
                ShopRepository.remove_user_purchase(db, user_id, SHOP_ITEMS["unlimited_transfers"])
                db.commit()

                await callback.message.edit_text(
                    f"✅ **ЛИМИТ ПЕРЕВОДОВ УСТАНОВЛЕН!**\n\n"
                    f"👤 **Пользователь:** {self._get_user_display_name(user)} (`{user_id}`)\n"
                    f"👮‍♂️ **Администратор:** {callback.from_user.first_name}\n\n"
                    f"_Пользователь теперь ограничен стандартными лимитами переводов_",
                    parse_mode="Markdown"
                )

                admin_id = callback.from_user.id
                self.logger.info(f"Админ {admin_id} установил лимит переводов пользователю {user_id}")

            except Exception as db_error:
                db.rollback()
                self.logger.error(f"Ошибка БД в handle_limit_button: {db_error}")
                await callback.message.edit_text(
                    "❌ **ОШИБКА БАЗЫ ДАННЫХ!**\n\n"
                    "Не удалось установить лимит. Попробуйте позже.",
                    parse_mode="Markdown"
                )

            db.close()
            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в handle_limit_button: {e}")
            await callback.answer("⚠️ Ошибка при установке лимита")

    async def handle_history_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки История операций"""
        try:
            user_id = int(callback.data.split('_')[-1])

            keyboard = types.InlineKeyboardMarkup(row_width=2)

            keyboard.row(
                types.InlineKeyboardButton("📊 Вся история", callback_data=f"history_all_0_{user_id}"),
                types.InlineKeyboardButton("✅ Выигрыши", callback_data=f"history_wins_0_{user_id}")
            )

            keyboard.row(
                types.InlineKeyboardButton("❌ Проигрыши", callback_data=f"history_losses_0_{user_id}"),
                types.InlineKeyboardButton("🔄 Переводы", callback_data=f"history_transfers_0_{user_id}")
            )

            keyboard.add(
                types.InlineKeyboardButton("⬅️ Назад", callback_data=f"user_back_{user_id}")
            )

            await callback.message.edit_text(
                f"📋 **ИСТОРИЯ ОПЕРАЦИЙ ПОЛЬЗОВАТЕЛЯ**\n\n"
                f"👤 **Пользователь:** `{user_id}`\n\n"
                f"📊 **Выберите тип операций:**\n"
                f"• `📊 Вся история` - все операции\n"
                f"• `✅ Выигрыши` - только выигрыши\n"
                f"• `❌ Проигрыши` - только проигрыши\n"
                f"• `🔄 Переводы` - переводы монет\n\n"
                f"_Будет показано по 20 операций за раз_",
                parse_mode="Markdown",
                reply_markup=keyboard
            )

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в handle_history_button: {e}")
            await callback.answer("⚠️ Ошибка при загрузке истории")

    async def show_user_history(self, callback: types.CallbackQuery):
        """Показывает историю операций пользователя с пагинацией"""
        try:
            data_parts = callback.data.split('_')

            if len(data_parts) < 4:
                await callback.answer("⚠️ Ошибка формата данных", show_alert=True)
                return

            history_type = data_parts[1]
            page = int(data_parts[2])
            user_id = int(data_parts[3])

            self.logger.info(f"Запрос истории: тип={history_type}, страница={page}, пользователь={user_id}")

            db = next(get_db())

            try:
                complete_history = self.history_merge_handler.get_complete_history(
                    db,
                    user_id,
                    limit=1000
                )

                self.logger.info(f"Получено {len(complete_history)} записей")

                if not complete_history:
                    history_text = "📋 **ИСТОРИЯ ОПЕРАЦИЙ ПОЛЬЗОВАТЕЛЯ**\n\n"
                    history_text += f"👤 **Пользователь:** `{user_id}`\n\n"
                    history_text += "📭 _Операций не найдено_"

                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(
                        types.InlineKeyboardButton(
                            "⬅️ Назад",
                            callback_data=f"user_back_{user_id}"
                        )
                    )
                else:
                    sorted_history = sorted(
                        complete_history,
                        key=lambda x: self._extract_datetime_for_sorting(x),
                        reverse=True
                    )

                    filtered_history = self._filter_history_by_type_fixed(
                        sorted_history,
                        history_type
                    )

                    operations_per_page = 20
                    total_pages = (len(filtered_history) + operations_per_page - 1) // operations_per_page

                    if page < 0:
                        page = 0
                    elif page >= total_pages:
                        page = total_pages - 1

                    start_idx = page * operations_per_page
                    end_idx = start_idx + operations_per_page
                    page_entries = filtered_history[start_idx:end_idx]

                    history_text = self._format_history_with_pagination(
                        page_entries,
                        user_id,
                        history_type,
                        page,
                        total_pages,
                        len(filtered_history)
                    )

                    keyboard = self._create_history_pagination_keyboard(
                        history_type, page, total_pages, user_id
                    )

                if len(history_text) > 4000:
                    history_text = history_text[:3900] + "...\n\n⚠️ _Текст обрезан_"

                await callback.message.edit_text(
                    history_text,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )

            except Exception as history_error:
                self.logger.error(f"Ошибка получения истории: {history_error}", exc_info=True)

                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data=f"user_back_{user_id}"
                    )
                )

                await callback.message.edit_text(
                    "❌ **ОШИБКА ЗАГРУЗКИ ИСТОРИИ**\n\n"
                    "Не удалось получить историю операций. Попробуйте позже.",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )

            finally:
                db.close()

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в show_user_history: {e}", exc_info=True)
            await callback.answer("⚠️ Ошибка при загрузке истории")

    def _extract_datetime_for_sorting(self, entry):
        """Извлекает дату-время из записи для сортировки"""
        try:
            if hasattr(entry, 'date'):
                return entry.date
            elif hasattr(entry, 'datetime'):
                return entry.datetime
            elif isinstance(entry, dict):
                if 'timestamp' in entry:
                    return entry['timestamp']
                elif 'date' in entry:
                    return entry['date']
                elif 'datetime' in entry:
                    return entry['datetime']

                text = entry.get('text', '')
                import re
                date_time_match = re.search(r'\[(\d{1,2}\.\d{1,2} \d{1,2}:\d{2})\]', text)
                if date_time_match:
                    date_time_str = date_time_match.group(1)
                    try:
                        dt = datetime.strptime(date_time_str, "%d.%m %H:%M")
                        dt = dt.replace(year=datetime.now().year)
                        return dt
                    except:
                        pass

                time_match = re.search(r'\[(\d{1,2}:\d{2}:\d{2})\]', text)
                if time_match:
                    time_str = time_match.group(1)
                    try:
                        today = datetime.now().date()
                        time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
                        return datetime.combine(today, time_obj)
                    except:
                        pass

            return datetime.min
        except Exception as e:
            print(f"❌ Ошибка извлечения даты: {e}")
            return datetime.min

    def _format_history_with_pagination(self, history_entries, user_id: int,
                                        history_type: str, page: int,
                                        total_pages: int, total_operations: int):
        """Форматирует историю с информацией о пагинации"""
        type_names = {
            "all": "Все операции",
            "wins": "Выигрыши",
            "losses": "Проигрыши",
            "transfers": "Переводы"
        }

        title = f"📋 **ИСТОРИЯ ОПЕРАЦИЙ**\n"
        title += f"👤 **ID:** `{user_id}`\n"
        title += f"📊 **Тип:** {type_names.get(history_type, 'Все операции')}\n"
        title += f"📄 **Страница:** {page + 1}/{total_pages}\n"
        title += f"📈 **Всего операций:** {total_operations}\n"

        if not history_entries:
            return title + "\n📭 _Операций не найдено_"

        history_lines = []
        entry_number = page * 20 + 1

        for entry in history_entries:
            text = entry.get('text', '')

            if len(text) > 80:
                text = text[:77] + "..."

            history_lines.append(f"{entry_number}. {text}")
            entry_number += 1

        history_text = title + "\n" + "\n".join(history_lines)

        return history_text

    def _create_history_pagination_keyboard(self, history_type: str, page: int,
                                            total_pages: int, user_id: int):
        """Создает клавиатуру с пагинацией для истории"""
        keyboard = types.InlineKeyboardMarkup(row_width=3)
        buttons = []

        if page > 0:
            buttons.append(
                types.InlineKeyboardButton(
                    "◀️ Назад",
                    callback_data=f"history_{history_type}_{page - 1}_{user_id}"
                )
            )

        buttons.append(
            types.InlineKeyboardButton(
                f"📄 {page + 1}",
                callback_data="history_current"
            )
        )

        if page < total_pages - 1:
            buttons.append(
                types.InlineKeyboardButton(
                    "Вперёд ▶️",
                    callback_data=f"history_{history_type}_{page + 1}_{user_id}"
                )
            )

        if buttons:
            keyboard.row(*buttons)

        keyboard.row(
            types.InlineKeyboardButton("📊 Меню", callback_data=f"user_history_{user_id}"),
            types.InlineKeyboardButton("⬅️ Назад", callback_data=f"user_back_{user_id}")
        )

        return keyboard

    def _filter_history_by_type_fixed(self, history_entries, history_type: str):
        """Фильтрует историю по типу операций"""
        if history_type == "all":
            return history_entries

        filtered = []
        for entry in history_entries:
            text = entry.get('text', '')

            if history_type == "wins":
                if '+' in text or 'Выигрыш' in text or 'Попадание' in text or 'Выпал' in text:
                    filtered.append(entry)

            elif history_type == "losses":
                if '-' in text and ('Проигрыш' in text or 'Ставка' in text):
                    filtered.append(entry)

            elif history_type == "transfers":
                if '💸 Перевод:' in text or '💰 Получено:' in text:
                    filtered.append(entry)

        return filtered

    async def handle_back_button(self, callback: types.CallbackQuery):
        """Обработчик кнопки Назад"""
        try:
            user_id = int(callback.data.split('_')[-1])

            await self._display_user_info_edit(callback.message, user_id, callback.from_user)

            await callback.answer()

        except Exception as e:
            self.logger.error(f"Ошибка в handle_back_button: {e}")
            await callback.answer("⚠️ Ошибка возврата")

    async def _display_user_info_edit(self, message: types.Message, user_id: int, from_user: types.User):
        """Редактирует сообщение с информацией о пользователе"""
        try:
            db = next(get_db())
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                await message.edit_text(f"⚠️ Пользователь с ID {user_id} не найден")
                db.close()
                return

            max_loss = self._get_user_max_loss(db, user_id)

            info_text = (
                f"👤 **ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ**\n\n"
                f"**ID:** `{user_id}`\n"
                f"**Имя:** {self._get_user_display_name(user)}\n\n"
                f"💰 **Баланс:** {format_number(user.coins)} монет\n"
                f"✅ **Выиграно всего:** {format_number(user.win_coins or 0)} монет\n"
                f"❌ **Проиграно всего:** {format_number(user.defeat_coins or 0)} монет\n"
                f"🎯 **Максимальная ставка:** {format_number(user.max_bet or 0)} монет\n"
                f"📉 **Максимальный проигрыш:** {format_number(max_loss)} монет\n"
                f"📈 **Максимальный выигрыш:** {format_number(user.max_win_coins or 0)} монет\n"
            )

            try:
                is_banned = mute_ban_manager.bot_ban_manager.is_user_bot_banned(user_id)
                if is_banned:
                    info_text += f"\n🚫 **Статус:** Забанен в боте"
            except Exception as e:
                self.logger.warning(f"Не удалось проверить бан: {e}")

            if hasattr(user, 'created_at') and user.created_at:
                info_text += f"\n📅 **Зарегистрирован:** {user.created_at.strftime('%d.%m.%Y %H:%M')}"

            keyboard = self._create_user_info_keyboard(user_id)

            await message.edit_text(info_text, parse_mode="Markdown", reply_markup=keyboard)
            db.close()

        except Exception as e:
            self.logger.error(f"Ошибка в _display_user_info_edit: {e}")
            try:
                await message.edit_text("⚠️ Ошибка формирования информации")
            except:
                pass
            try:
                db.close()
            except:
                pass

    async def handle_ban_reason(self, message: types.Message, state: FSMContext):
        """Обработка причины бана"""
        try:
            if message.text and message.text.lower() == '/cancel':
                await state.finish()
                await message.answer("❌ Бан отменен")
                return

            reason = message.text
            data = await state.get_data()
            user_id = data.get('ban_user_id')

            if not user_id:
                await message.answer("⚠️ Ошибка: не найден ID пользователя")
                await state.finish()
                return

            if not reason or len(reason.strip()) < 3:
                await message.answer("⚠️ Причина должна содержать минимум 3 символа")
                return

            reason = reason.strip()

            admin_id = message.from_user.id

            success = await mute_ban_manager.ban_in_bot(
                user_id=user_id,
                admin_id=admin_id,
                reason=reason,
                seconds=None
            )

            if success:
                try:
                    await message.bot.send_message(
                        chat_id=user_id,
                        text=f"🚫 Вы забанены в боте.\nПричина: {reason}"
                    )
                except:
                    pass

                await message.answer(
                    f"✅ **ПОЛЬЗОВАТЕЛЬ ЗАБАНЕН В БОТЕ!**\n\n"
                    f"👤 **ID:** `{user_id}`\n"
                    f"📝 **Причина:** {reason}\n"
                    f"👮‍♂️ **Администратор:** {message.from_user.first_name}\n\n"
                    f"_Пользователь получил уведомление о бане_",
                    parse_mode="Markdown"
                )

                self.logger.info(f"Админ {admin_id} забанил пользователя {user_id} в боте. Причина: {reason}")
            else:
                await message.answer(
                    "❌ **ОШИБКА ПРИ БАНЕ В БОТЕ!**\n\n"
                    "Не удалось забанить пользователя. Возможно, он является администратором бота.",
                    parse_mode="Markdown"
                )

            await state.finish()

        except Exception as e:
            self.logger.error(f"Ошибка в handle_ban_reason: {e}")
            await message.answer("⚠️ Ошибка обработки причины бана")
            await state.finish()

    async def handle_profile_command(self, message: types.Message):
        """Единый обработчик для команды /profile"""
        if not await check_admin_async(message):
            return

        try:
            command_text = message.text.strip()

            # Случай 1: /profile (без параметров) с reply
            if command_text == '/profile' or command_text == '/profile@swagroulette_bot':
                if message.reply_to_message and message.reply_to_message.from_user:
                    user_id = message.reply_to_message.from_user.id
                    await self._display_user_info(message, user_id)
                else:
                    help_text = (
                        "🔍 **ИСПОЛЬЗОВАНИЕ КОМАНДЫ /profile**\n\n"
                        "**Способ 1 (с ID):**\n"
                        "`/profile 123456789` - просмотр информации по ID\n\n"
                        "**Способ 2 (ответом):**\n"
                        "1. Ответьте на сообщение пользователя\n"
                        "2. Отправьте `/profile`\n\n"
                        "**Примеры:**\n"
                        "• `/profile 123456789`\n"
                        "• Ответ на сообщение + `/profile`\n\n"
                        "👮‍♂️ *Только для администраторов*"
                    )
                    await message.answer(help_text, parse_mode="Markdown")
                return

            # Случай 2: /profile <ID>
            if command_text.startswith('/profile ') or command_text.startswith('/profile@swagroulette_bot '):
                # Извлекаем ID
                parts = command_text.split()
                if len(parts) < 2:
                    await message.answer("⚠️ Укажите ID пользователя: `/profile 123456789`", parse_mode="Markdown")
                    return

                potential_id = parts[1].strip()

                if not potential_id.isdigit():
                    await message.answer("⚠️ ID должен быть числом", parse_mode="Markdown")
                    return

                user_id = int(potential_id)

                if user_id <= 0 or user_id > 9223372036854775807:
                    await message.answer("⚠️ Неверный ID пользователя")
                    return

                await self._display_user_info(message, user_id)
                return

        except ValueError:
            await message.answer("⚠️ ID должен быть числом")
        except Exception as e:
            self.logger.error(f"Ошибка в handle_profile_command: {e}")
            await message.answer("⚠️ Ошибка получения информации")


def register_user_info_handlers(dp: Dispatcher):
    """Регистрирует обработчики для команды /profile"""
    handler = UserDataDisplay()

    # Один хендлер для всех случаев команды /profile
    dp.register_message_handler(
        handler.handle_profile_command,
        commands=['profile']
    )

    # Callback обработчики для кнопок
    dp.register_callback_query_handler(
        handler.handle_reset_button,
        lambda c: c.data.startswith("user_reset_")
    )

    dp.register_callback_query_handler(
        handler.handle_reset_confirm,
        lambda c: c.data.startswith("reset_")
    )

    dp.register_callback_query_handler(
        handler.execute_reset,
        lambda c: c.data.startswith("confirm_reset_")
    )

    dp.register_callback_query_handler(
        handler.handle_ban_button,
        lambda c: c.data.startswith("user_ban_")
    )

    dp.register_callback_query_handler(
        handler.handle_unban_button,
        lambda c: c.data.startswith("user_unban_")
    )

    dp.register_callback_query_handler(
        handler.handle_unlimit_button,
        lambda c: c.data.startswith("user_unlimit_")
    )

    dp.register_callback_query_handler(
        handler.handle_limit_button,
        lambda c: c.data.startswith("user_limit_")
    )

    dp.register_callback_query_handler(
        handler.handle_history_button,
        lambda c: c.data.startswith("user_history_")
    )

    dp.register_callback_query_handler(
        handler.show_user_history,
        lambda c: c.data.startswith("history_")
    )

    dp.register_callback_query_handler(
        handler.handle_back_button,
        lambda c: c.data.startswith("user_back_")
    )

    # FSM для ввода причины бана
    dp.register_message_handler(
        handler.handle_ban_reason,
        state=UserInfoStates.waiting_for_ban_reason
    )

    logger.info("✅ Обработчики команды /profile зарегистрированы")
    return handler