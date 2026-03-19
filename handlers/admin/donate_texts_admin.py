"""
Админские команды для управления текстами доната.
Доступно для: главных админов и админов из БД
"""

import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from handlers.donate.texts_simple import donate_texts
from .admin_helpers import check_admin_async, check_admin_silent

logger = logging.getLogger(__name__)


class DonateTextStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_confirmation = State()


class DonateTextsAdmin:
    """Обработчик админских команд для текстов доната"""

    async def donate_texts_menu(self, message: types.Message):
        """Меню управления текстами доната"""
        if not await check_admin_async(message):
            return

        keyboard = InlineKeyboardMarkup(row_width=1)

        # Ключи текстов с описаниями
        text_options = [
            ("main", "📋 Основной текст доната (/донат)"),
            ("buy_coins", "🛒 Текст покупки монет"),
            ("bonus", "🎁 Текст бонусной системы"),
            ("privileges", "👑 Текст привилегий"),
            ("daily_bonus", "💰 Текст ежедневного бонуса (50K)"),
            ("privilege_bonus", "💎 Текст бонусов за привилегии"),
            ("purchase_item", "💳 Текст покупки привилегии"),
            ("already_bought", "✅ Текст уже купленной привилегии"),
            ("bonus_claimed", "🎉 Текст после получения бонуса"),
            ("error_text", "❌ Текст ошибки")
        ]

        for key, description in text_options:
            keyboard.add(InlineKeyboardButton(
                text=description,
                callback_data=f"donate_text_{key}"
            ))

        keyboard.add(
            InlineKeyboardButton("📄 Показать все тексты", callback_data="donate_show_all"),
            InlineKeyboardButton("🔄 Сбросить все", callback_data="donate_reset_all")
        )

        await message.answer(
            "📝 <b>Управление текстами доната</b>\n\n"
            "Выберите текст для редактирования:\n"
            "👮‍♂️ <i>Доступно для всех администраторов</i>",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    async def handle_text_selection(self, callback: types.CallbackQuery):
        """Обработчик выбора текста"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ У вас нет прав администратора", show_alert=True)
            return

        try:
            key = callback.data.split("_")[-1]
            current_text = donate_texts.get(key)

            # Сохраняем ключ в state
            state = Dispatcher.get_current().current_state()
            await state.update_data(text_key=key, current_text=current_text)
            await DonateTextStates.waiting_for_text.set()

            # Показываем текущий текст
            preview = current_text[:500] + "..." if len(current_text) > 500 else current_text

            await callback.message.edit_text(
                f"✏️ <b>Редактирование текста</b>\n\n"
                f"🔑 Ключ: <code>{key}</code>\n\n"
                f"📄 <b>Текущий текст:</b>\n"
                f"<code>{preview}</code>\n\n"
                f"⬇️ <b>Пришлите новый текст:</b>\n"
                f"• Можно использовать HTML разметку\n"
                f"• Нажмите /cancel для отмены",
                parse_mode="HTML"
            )

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при выборе текста: {e}")
            await callback.answer("❌ Ошибка при выборе текста", show_alert=True)

    async def receive_new_text(self, message: types.Message, state: FSMContext):
        """Принимает новый текст от админа и предлагает предпросмотр"""
        if not await check_admin_async(message):
            await state.finish()
            return

        # Проверяем команду /cancel
        if message.text and message.text.lower() in ['/cancel', '/отмена']:
            await self.cancel_edit(message, state)
            return

        try:
            data = await state.get_data()
            key = data.get('text_key')

            if not key:
                await message.answer("❌ Ошибка: ключ текста не найден")
                await state.finish()
                return

            new_text = message.text

            if len(new_text.strip()) < 10:
                await message.answer("❌ Текст слишком короткий (минимум 10 символов)")
                return

            # Сохраняем текст в state для подтверждения
            await state.update_data(new_text=new_text)

            # Показываем предпросмотр и кнопки подтверждения
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("✅ Подтвердить", callback_data="donate_text_confirm"),
                InlineKeyboardButton("👁️ Предпросмотр", callback_data="donate_text_preview"),
                InlineKeyboardButton("✏️ Редактировать", callback_data=f"donate_text_editagain_{key}"),
                InlineKeyboardButton("❌ Отмена", callback_data="donate_text_cancel")
            )

            # Создаем безопасный предпросмотр (обрезаем если длинный)
            preview = new_text[:300] + "..." if len(new_text) > 300 else new_text

            await message.answer(
                f"📝 <b>Новый текст готов!</b>\n\n"
                f"🔑 Ключ: <code>{key}</code>\n\n"
                f"📄 <b>Предпросмотр:</b>\n"
                f"<code>{preview}</code>\n\n"
                f"📏 <b>Длина:</b> {len(new_text)} символов\n\n"
                f"💡 <b>Выберите действие:</b>",
                parse_mode="HTML",
                reply_markup=keyboard
            )

            # Переходим в состояние ожидания подтверждения
            await DonateTextStates.waiting_for_confirmation.set()

        except Exception as e:
            logger.error(f"Ошибка при получении текста: {e}")
            await message.answer("❌ Ошибка обработки текста")
            await state.finish()

    async def handle_text_preview(self, callback: types.CallbackQuery, state: FSMContext):
        """Показывает полный предпросмотр текста"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ Нет прав", show_alert=True)
            return

        try:
            data = await state.get_data()
            new_text = data.get('new_text')
            key = data.get('text_key')

            if not new_text:
                await callback.answer("❌ Текст не найден", show_alert=True)
                return

            # Показываем полный предпросмотр
            try:
                # Пробуем отправить как HTML для проверки разметки
                await callback.message.answer(
                    f"👁️ <b>ПРЕДПРОСМОТР ТЕКСТА</b>\n\n"
                    f"{new_text}",
                    parse_mode="HTML"
                )

                # Сообщаем, что предпросмотр показан
                await callback.answer("✅ Предпросмотр отправлен отдельным сообщением")
            except Exception as e:
                # Если ошибка разметки, показываем в коде
                error_preview = new_text[:500] + "..." if len(new_text) > 500 else new_text
                await callback.message.answer(
                    f"⚠️ <b>ОШИБКА РАЗМЕТКИ HTML</b>\n\n"
                    f"❌ Не удалось отобразить текст с HTML разметкой.\n\n"
                    f"📋 <b>Текст в формате кода:</b>\n"
                    f"<code>{error_preview}</code>\n\n"
                    f"🔍 <b>Ошибка:</b> {str(e)[:100]}",
                    parse_mode="HTML"
                )
                await callback.answer("⚠️ Обнаружена ошибка HTML разметки")

        except Exception as e:
            logger.error(f"Ошибка при показе предпросмотра: {e}")
            await callback.answer("❌ Ошибка предпросмотра", show_alert=True)

    async def handle_text_confirm(self, callback: types.CallbackQuery, state: FSMContext):
        """Подтверждает сохранение текста"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ Нет прав", show_alert=True)
            return

        try:
            data = await state.get_data()
            key = data.get('text_key')
            new_text = data.get('new_text')

            if not key or not new_text:
                await callback.answer("❌ Данные не найдены", show_alert=True)
                return

            # 🔧 ИСПРАВЛЕНИЕ: Если ключ "coins", меняем на "buy_coins"
            if key == "coins":
                logger.info(f"Исправляем ключ: 'coins' -> 'buy_coins'")
                key = "buy_coins"

            # Сохраняем текст
            success = donate_texts.set(key, new_text)

            if success:
                preview = new_text[:300] + "..." if len(new_text) > 300 else new_text

                await callback.message.edit_text(
                    f"✅ <b>Текст успешно сохранен!</b>\n\n"
                    f"🔑 Ключ: <code>{key}</code>\n\n"
                    f"📋 <b>Предпросмотр:</b>\n"
                    f"<code>{preview}</code>\n\n"
                    f"📏 <b>Длина:</b> {len(new_text)} символов\n\n"
                    f"💡 Текст уже обновлен для всех пользователей!\n"
                    f"🔄 Чтобы проверить, откройте /донат",
                    parse_mode="HTML"
                )

                logger.info(f"Admin {callback.from_user.id} сохранил текст '{key}'")
            else:
                await callback.message.edit_text(
                    "❌ <b>Ошибка сохранения текста!</b>\n\n"
                    "Попробуйте позже или обратитесь к разработчику.",
                    parse_mode="HTML"
                )

            await state.finish()
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при сохранении текста: {e}")
            await callback.answer("❌ Ошибка сохранения", show_alert=True)
            await state.finish()

    async def handle_text_edit_again(self, callback: types.CallbackQuery, state: FSMContext):
        """Возвращает к редактированию текста"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ Нет прав", show_alert=True)
            return

        try:
            key = callback.data.split("_")[-1]
            data = await state.get_data()
            current_text = data.get('new_text') or data.get('current_text')

            await state.update_data(text_key=key)
            await DonateTextStates.waiting_for_text.set()

            preview = current_text[:500] + "..." if len(current_text) > 500 else current_text

            await callback.message.edit_text(
                f"✏️ <b>Редактирование текста</b>\n\n"
                f"🔑 Ключ: <code>{key}</code>\n\n"
                f"📄 <b>Текущий текст:</b>\n"
                f"<code>{preview}</code>\n\n"
                f"⬇️ <b>Пришлите новый текст:</b>\n"
                f"• Можно использовать HTML разметку\n"
                f"• Нажмите /cancel для отмены",
                parse_mode="HTML"
            )

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при возврате к редактированию: {e}")
            await callback.answer("❌ Ошибка", show_alert=True)

    async def handle_text_cancel(self, callback: types.CallbackQuery, state: FSMContext):
        """Отмена редактирования текста"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ Нет прав", show_alert=True)
            return

        try:
            await state.finish()
            await callback.message.edit_text(
                "❌ <b>Редактирование отменено</b>\n\n"
                "Текст не был сохранен.",
                parse_mode="HTML"
            )
            await callback.answer("❌ Отменено")
        except Exception as e:
            logger.error(f"Ошибка при отмене: {e}")
            await callback.answer("❌ Ошибка")

    async def show_all_texts(self, callback: types.CallbackQuery):
        """Показывает все тексты"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ У вас нет прав администратора", show_alert=True)
            return

        try:
            all_texts = donate_texts.list_all()

            if not all_texts:
                await callback.message.edit_text(
                    "📋 <b>Тексты доната:</b>\n\n"
                    "ℹ️ Тексты не найдены",
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            response = ["📋 <b>Все тексты доната:</b>\n"]

            for key, text in all_texts.items():
                preview = text[:80].replace('<', '&lt;').replace('>', '&gt;') + "..." if len(text) > 80 else text.replace('<', '&lt;').replace('>', '&gt;')
                length = len(text)

                response.append(f"\n🔑 <code>{key}</code>")
                response.append(f"📏 {length} символов")
                response.append(f"📄 {preview}")
                response.append("─" * 30)

            # Отправляем частями если слишком длинно
            full_text = "\n".join(response)
            if len(full_text) > 4000:
                parts = []
                current = ""
                for line in response:
                    if len(current) + len(line) + 1 < 4000:
                        current += "\n" + line if current else line
                    else:
                        parts.append(current)
                        current = line
                if current:
                    parts.append(current)

                for i, part in enumerate(parts):
                    if i == 0:
                        await callback.message.edit_text(part, parse_mode="HTML")
                    else:
                        await callback.message.answer(part, parse_mode="HTML")
            else:
                await callback.message.edit_text(full_text, parse_mode="HTML")

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при показе текстов: {e}")
            await callback.message.edit_text(
                "❌ <b>Ошибка при загрузке текстов</b>\n\n"
                f"<code>{str(e)[:200]}</code>",
                parse_mode="HTML"
            )
            await callback.answer("❌ Ошибка")

    async def reset_all_texts(self, callback: types.CallbackQuery):
        """Сбрасывает все тексты"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ У вас нет прав администратора", show_alert=True)
            return

        try:
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton("✅ Да, сбросить все", callback_data="donate_reset_all_confirm"),
                InlineKeyboardButton("❌ Нет, отмена", callback_data="donate_text_menu")
            )

            await callback.message.edit_text(
                "⚠️ <b>СБРОС ВСЕХ ТЕКСТОВ</b>\n\n"
                "‼️ Вы уверены, что хотите сбросить ВСЕ тексты доната к значениям по умолчанию?\n\n"
                "📝 <b>Будут сброшены:</b>\n"
                "• Все тексты доната\n"
                "• Все уведомления\n"
                "• Все сообщения\n\n"
                "🔄 <b>Это действие нельзя отменить!</b>",
                parse_mode="HTML",
                reply_markup=keyboard
            )

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при сбросе текстов: {e}")
            await callback.answer("❌ Ошибка", show_alert=True)

    async def reset_all_confirm(self, callback: types.CallbackQuery):
        """Подтверждение сброса всех текстов"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ У вас нет прав администратора", show_alert=True)
            return

        try:
            success = donate_texts.reset_all()

            if success:
                await callback.message.edit_text(
                    "✅ <b>Все тексты сброшены к значениям по умолчанию!</b>\n\n"
                    "🔄 Все изменения отменены.\n"
                    "📝 Тексты восстановлены к первоначальному виду.",
                    parse_mode="HTML"
                )
                logger.info(f"Admin {callback.from_user.id} сбросил все тексты доната")
            else:
                await callback.message.edit_text(
                    "❌ <b>Ошибка сброса текстов!</b>\n\n"
                    "Попробуйте позже или обратитесь к разработчику.",
                    parse_mode="HTML"
                )

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при подтверждении сброса: {e}")
            await callback.answer("❌ Ошибка", show_alert=True)

    async def back_to_menu(self, callback: types.CallbackQuery):
        """Возврат в меню"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ Нет прав", show_alert=True)
            return

        await self.donate_texts_menu(callback.message)
        await callback.answer()

    async def cancel_edit(self, message: types.Message, state: FSMContext):
        """Отмена редактирования через команду"""
        if not await check_admin_async(message):
            await state.finish()
            return

        await state.finish()
        await message.answer(
            "❌ <b>Редактирование отменено</b>\n\n"
            "Текст не был сохранен.",
            parse_mode="HTML"
        )


def register_donate_texts_admin(dp: Dispatcher):
    """Регистрирует обработчики для управления текстами доната"""
    handler = DonateTextsAdmin()

    # Команды
    dp.register_message_handler(
        handler.donate_texts_menu,
        commands=['текста_доната', 'donate_texts', 'тексты']
    )

    # Текстовые команды
    dp.register_message_handler(
        handler.donate_texts_menu,
        lambda m: m.text and m.text.lower().strip() in [
            'текста доната', 'тексты доната', 'редактировать текст доната',
            'донат тексты', 'donate texts'
        ]
    )

    # FSM для получения текста
    dp.register_message_handler(
        handler.receive_new_text,
        state=DonateTextStates.waiting_for_text
    )

    # Callback обработчики
    dp.register_callback_query_handler(
        handler.handle_text_selection,
        lambda c: c.data.startswith("donate_text_") and not any(x in c.data for x in ['confirm', 'preview', 'editagain', 'cancel']),
        state="*"
    )

    dp.register_callback_query_handler(
        handler.handle_text_preview,
        lambda c: c.data == "donate_text_preview",
        state=DonateTextStates.waiting_for_confirmation
    )

    dp.register_callback_query_handler(
        handler.handle_text_confirm,
        lambda c: c.data == "donate_text_confirm",
        state=DonateTextStates.waiting_for_confirmation
    )

    dp.register_callback_query_handler(
        handler.handle_text_edit_again,
        lambda c: c.data.startswith("donate_text_editagain_"),
        state=DonateTextStates.waiting_for_confirmation
    )

    dp.register_callback_query_handler(
        handler.handle_text_cancel,
        lambda c: c.data == "donate_text_cancel",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.show_all_texts,
        lambda c: c.data == "donate_show_all",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.reset_all_texts,
        lambda c: c.data == "donate_reset_all",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.reset_all_confirm,
        lambda c: c.data == "donate_reset_all_confirm",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.back_to_menu,
        lambda c: c.data == "donate_text_menu",
        state="*"
    )

    logger.info("✅ Обработчики текстов доната зарегистрированы")