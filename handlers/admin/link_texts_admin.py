"""
Админские команды для управления текстом ссылок.
"""

import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from handlers.link_texts_simple import link_texts
from .admin_helpers import check_admin_async, check_admin_silent

logger = logging.getLogger(__name__)


class LinkTextStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_confirmation = State()


class LinkTextsAdmin:
    """Обработчик админских команд для текста ссылок"""

    async def links_text_menu(self, message: types.Message):
        """Меню управления текстом ссылок"""
        if not await check_admin_async(message):
            return

        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("✏️ Редактировать текст ссылок", callback_data="admin_edit_links_text"),
            InlineKeyboardButton("📄 Показать текущий текст", callback_data="admin_show_links_text"),
            InlineKeyboardButton("🔄 Сбросить к стандартному", callback_data="admin_reset_links_text")
        )

        await message.answer(
            "🔗 <b>Управление текстом ссылок</b>\n\n"
            "Выберите действие для текста ссылок (команда /ссылки):\n"
            "👮‍♂️ <i>Доступно для всех администраторов</i>",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    async def handle_show_links_text(self, callback: types.CallbackQuery):
        """Показывает текущий текст ссылок"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ У вас нет прав администратора", show_alert=True)
            return

        try:
            text = link_texts.get()
            preview = text[:500] + "..." if len(text) > 500 else text

            await callback.message.edit_text(
                f"🔗 <b>Текущий текст ссылок:</b>\n\n"
                f"📏 Длина: {len(text)} символов\n\n"
                f"📄 <b>Предпросмотр:</b>\n"
                f"<code>{preview}</code>\n\n"
                f"💡 Используйте кнопки для управления",
                parse_mode="HTML",
                reply_markup=self._get_back_keyboard()
            )
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при показе текста ссылок: {e}")
            await callback.answer("❌ Ошибка при загрузке текста", show_alert=True)

    async def handle_edit_links_text(self, callback: types.CallbackQuery):
        """Начинает редактирование текста ссылок"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ У вас нет прав администратора", show_alert=True)
            return

        try:
            current_text = link_texts.get()
            preview = current_text[:500] + "..." if len(current_text) > 500 else current_text

            # Сохраняем в state
            state = Dispatcher.get_current().current_state()
            await state.update_data(current_text=current_text)
            await LinkTextStates.waiting_for_text.set()

            await callback.message.edit_text(
                f"✏️ <b>Редактирование текста ссылок</b>\n\n"
                f"📏 Текущая длина: {len(current_text)} символов\n\n"
                f"📄 <b>Текущий текст:</b>\n"
                f"<code>{preview}</code>\n\n"
                f"⬇️ <b>Пришлите новый текст:</b>\n"
                f"• Можно использовать Markdown разметку\n"
                f"• Поддерживаются ссылки [текст](url)\n"
                f"• Нажмите /cancel для отмены",
                parse_mode="HTML"
            )
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при начале редактирования: {e}")
            await callback.answer("❌ Ошибка при начале редактирования", show_alert=True)

    async def receive_new_text(self, message: types.Message, state: FSMContext):
        """Принимает новый текст от админа"""
        if not await check_admin_async(message):
            await state.finish()
            return

        # Проверяем команду /cancel
        if message.text and message.text.lower() in ['/cancel', '/отмена']:
            await self.cancel_edit(message, state)
            return

        try:
            new_text = message.text

            if len(new_text.strip()) < 10:
                await message.answer("❌ Текст слишком короткий (минимум 10 символов)")
                return

            # Сохраняем текст в state
            await state.update_data(new_text=new_text)

            # Показываем предпросмотр
            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("✅ Подтвердить", callback_data="admin_links_text_confirm"),
                InlineKeyboardButton("👁️ Предпросмотр", callback_data="admin_links_text_preview"),
                InlineKeyboardButton("✏️ Редактировать снова", callback_data="admin_edit_links_text"),
                InlineKeyboardButton("❌ Отмена", callback_data="admin_links_text_cancel")
            )

            preview = new_text[:300] + "..." if len(new_text) > 300 else new_text

            await message.answer(
                f"📝 <b>Новый текст готов!</b>\n\n"
                f"📏 <b>Длина:</b> {len(new_text)} символов\n\n"
                f"📄 <b>Предпросмотр:</b>\n"
                f"<code>{preview}</code>\n\n"
                f"💡 <b>Выберите действие:</b>",
                parse_mode="HTML",
                reply_markup=keyboard
            )

            await LinkTextStates.waiting_for_confirmation.set()

        except Exception as e:
            logger.error(f"Ошибка при получении текста: {e}")
            await message.answer("❌ Ошибка обработки текста")
            await state.finish()

    async def handle_preview(self, callback: types.CallbackQuery, state: FSMContext):
        """Показывает полный предпросмотр текста"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ Нет прав", show_alert=True)
            return

        try:
            data = await state.get_data()
            new_text = data.get('new_text')

            if not new_text:
                await callback.answer("❌ Текст не найден", show_alert=True)
                return

            # Показываем предпросмотр с Markdown
            try:
                await callback.message.answer(
                    f"👁️ <b>ПРЕДПРОСМОТР ТЕКСТА ССЫЛОК</b>\n\n"
                    f"{new_text}",
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer("✅ Предпросмотр отправлен отдельным сообщением")
            except Exception as e:
                # Если ошибка Markdown
                error_preview = new_text[:500] + "..." if len(new_text) > 500 else new_text
                await callback.message.answer(
                    f"⚠️ <b>ОШИБКА РАЗМЕТКИ MARKDOWN</b>\n\n"
                    f"❌ Не удалось отобразить текст с Markdown разметкой.\n\n"
                    f"📋 <b>Текст в формате кода:</b>\n"
                    f"<code>{error_preview}</code>\n\n"
                    f"🔍 <b>Ошибка:</b> {str(e)[:100]}",
                    parse_mode="HTML"
                )
                await callback.answer("⚠️ Обнаружена ошибка Markdown разметки")

        except Exception as e:
            logger.error(f"Ошибка при показе предпросмотра: {e}")
            await callback.answer("❌ Ошибка предпросмотра", show_alert=True)

    async def handle_confirm(self, callback: types.CallbackQuery, state: FSMContext):
        """Подтверждает сохранение текста"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ Нет прав", show_alert=True)
            return

        try:
            data = await state.get_data()
            new_text = data.get('new_text')

            if not new_text:
                await callback.answer("❌ Данные не найдены", show_alert=True)
                return

            # Сохраняем текст
            success = link_texts.set(new_text)

            if success:
                preview = new_text[:300] + "..." if len(new_text) > 300 else new_text

                await callback.message.edit_text(
                    f"✅ <b>Текст ссылок успешно сохранен!</b>\n\n"
                    f"📏 <b>Длина:</b> {len(new_text)} символов\n\n"
                    f"📋 <b>Предпросмотр:</b>\n"
                    f"<code>{preview}</code>\n\n"
                    f"💡 Текст уже обновлен для всех пользователей!\n"
                    f"🔄 Чтобы проверить, откройте /ссылки",
                    parse_mode="HTML",
                    reply_markup=self._get_back_keyboard()
                )

                logger.info(f"Admin {callback.from_user.id} обновил текст ссылок")
            else:
                await callback.message.edit_text(
                    "❌ <b>Ошибка сохранения текста!</b>\n\n"
                    "Попробуйте позже или обратитесь к разработчику.",
                    parse_mode="HTML",
                    reply_markup=self._get_back_keyboard()
                )

            await state.finish()
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при сохранении текста: {e}")
            await callback.answer("❌ Ошибка сохранения", show_alert=True)
            await state.finish()

    async def handle_reset(self, callback: types.CallbackQuery):
        """Сбрасывает текст к стандартному"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ У вас нет прав администратора", show_alert=True)
            return

        try:
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton("✅ Да, сбросить", callback_data="admin_reset_links_confirm"),
                InlineKeyboardButton("❌ Нет, отмена", callback_data="admin_links_text_menu")
            )

            await callback.message.edit_text(
                "⚠️ <b>СБРОС ТЕКСТА ССЫЛОК</b>\n\n"
                "‼️ Вы уверены, что хотите сбросить текст ссылок к стандартному значению?\n\n"
                "🔄 <b>Это действие нельзя отменить!</b>",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при сбросе текста: {e}")
            await callback.answer("❌ Ошибка", show_alert=True)

    async def handle_reset_confirm(self, callback: types.CallbackQuery):
        """Подтверждение сброса текста"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ У вас нет прав администратора", show_alert=True)
            return

        try:
            success = link_texts.reset()

            if success:
                default_text = link_texts.get()
                preview = default_text[:300] + "..." if len(default_text) > 300 else default_text

                await callback.message.edit_text(
                    "✅ <b>Текст ссылок сброшен к стандартному значению!</b>\n\n"
                    f"📏 <b>Длина:</b> {len(default_text)} символов\n\n"
                    f"📋 <b>Предпросмотр:</b>\n"
                    f"<code>{preview}</code>\n\n"
                    f"🔄 Все изменения отменены.",
                    parse_mode="HTML",
                    reply_markup=self._get_back_keyboard()
                )
                logger.info(f"Admin {callback.from_user.id} сбросил текст ссылок")
            else:
                await callback.message.edit_text(
                    "❌ <b>Ошибка сброса текста!</b>\n\n"
                    "Попробуйте позже или обратитесь к разработчику.",
                    parse_mode="HTML",
                    reply_markup=self._get_back_keyboard()
                )

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при подтверждении сброса: {e}")
            await callback.answer("❌ Ошибка", show_alert=True)

    async def handle_cancel(self, callback: types.CallbackQuery, state: FSMContext):
        """Отмена редактирования"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ Нет прав", show_alert=True)
            return

        try:
            await state.finish()
            await callback.message.edit_text(
                "❌ <b>Редактирование отменено</b>\n\n"
                "Текст не был сохранен.",
                parse_mode="HTML",
                reply_markup=self._get_back_keyboard()
            )
            await callback.answer("❌ Отменено")
        except Exception as e:
            logger.error(f"Ошибка при отмене: {e}")
            await callback.answer("❌ Ошибка")

    async def back_to_menu(self, callback: types.CallbackQuery):
        """Возврат в меню"""
        if not await check_admin_silent(callback.from_user.id):
            await callback.answer("❌ Нет прав", show_alert=True)
            return

        await self.links_text_menu(callback.message)
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
            parse_mode="HTML",
            reply_markup=self._get_back_keyboard()
        )

    def _get_back_keyboard(self):
        """Возвращает клавиатуру с кнопкой назад"""
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="admin_links_text_menu"))
        return keyboard


def register_link_texts_admin(dp: Dispatcher):
    """Регистрирует обработчики для управления текстом ссылок"""
    handler = LinkTextsAdmin()

    # Команды
    dp.register_message_handler(
        handler.links_text_menu,
        commands=['текст_ссылок', 'links_text', 'ссылки_текст']
    )

    # Текстовые команды
    dp.register_message_handler(
        handler.links_text_menu,
        lambda m: m.text and m.text.lower().strip() in [
            'текст ссылок', 'редактировать ссылки', 'ссылки текст'
        ]
    )

    # FSM для получения текста
    dp.register_message_handler(
        handler.receive_new_text,
        state=LinkTextStates.waiting_for_text
    )

    # Callback обработчики
    dp.register_callback_query_handler(
        handler.handle_show_links_text,
        lambda c: c.data == "admin_show_links_text",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.handle_edit_links_text,
        lambda c: c.data == "admin_edit_links_text",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.handle_preview,
        lambda c: c.data == "admin_links_text_preview",
        state=LinkTextStates.waiting_for_confirmation
    )

    dp.register_callback_query_handler(
        handler.handle_confirm,
        lambda c: c.data == "admin_links_text_confirm",
        state=LinkTextStates.waiting_for_confirmation
    )

    dp.register_callback_query_handler(
        handler.handle_reset,
        lambda c: c.data == "admin_reset_links_text",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.handle_reset_confirm,
        lambda c: c.data == "admin_reset_links_confirm",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.handle_cancel,
        lambda c: c.data == "admin_links_text_cancel",
        state="*"
    )

    dp.register_callback_query_handler(
        handler.back_to_menu,
        lambda c: c.data == "admin_links_text_menu",
        state="*"
    )

    logger.info("✅ Обработчики текста ссылок зарегистрированы")