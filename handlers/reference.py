import binascii
import os
import math
from aiogram import types, Dispatcher
from aiogram.utils.deep_linking import get_start_link
from config import bot
from database import get_db
from database.crud import UserRepository, ReferenceRepository
from const import REFERENCE_MENU_TEXT, REFERENCE_LINK_TEXT
from keyboards.reference_keyboard import reference_menu_keyboard


async def reference_menu_call(call: types.CallbackQuery):
    await bot.send_message(
        chat_id=call.message.chat.id,
        text=REFERENCE_MENU_TEXT,
        reply_markup=reference_menu_keyboard(),
        parse_mode=types.ParseMode.MARKDOWN
    )


async def reference_link_call(call: types.CallbackQuery):
    db = next(get_db())
    try:
        user = UserRepository.get_user_by_telegram_id(db, call.from_user.id)

        if not user or not user.reference_link:
            token = binascii.hexlify(os.urandom(4)).decode()
            link = await get_start_link(payload=token)
            UserRepository.update_reference_link(db, call.from_user.id, link)
        else:
            link = user.reference_link

        await bot.send_message(
            chat_id=call.message.chat.id,
            text=REFERENCE_LINK_TEXT.format(link=link)
        )
    except Exception as e:
        print(f"❌ Ошибка создания реферальной ссылки: {e}")
    finally:
        db.close()


async def reference_list_call(call: types.CallbackQuery):
    db = next(get_db())
    try:
        # Получаем ВСЕХ рефералов пользователя
        references = ReferenceRepository.get_user_references(db, call.from_user.id)

        # Получаем общее количество рефералов
        total_referrals = len(references)

        # Определяем номер страницы из callback_data (если есть)
        page = 0
        if ":" in call.data:
            try:
                page = int(call.data.split(":")[1])
            except (ValueError, IndexError):
                page = 0

        # Настройки пагинации
        items_per_page = 10

        # Проверка корректности номера страницы
        max_page = max(0, math.ceil(total_referrals / items_per_page) - 1)
        if max_page < 0:
            max_page = 0

        if page < 0:
            page = 0
        elif page > max_page and max_page > 0:
            page = max_page

        # Вычисляем индексы для среза
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page

        # Получаем рефералов для текущей страницы
        page_references = references[start_idx:end_idx]

        if page_references:
            data = []
            for idx, ref in enumerate(page_references, start=start_idx + 1):
                # Получаем данные пользователя по ID
                user_data = UserRepository.get_user_by_telegram_id(db, ref.reference_telegram_id)
                if user_data:
                    # Создаем кликабельную ссылку на пользователя
                    username = user_data.username or user_data.first_name or f"Пользователь {ref.reference_telegram_id}"
                    data.append(f"{idx}. [{username}](tg://user?id={ref.reference_telegram_id})")
                else:
                    data.append(f"{idx}. [Пользователь удален](tg://user?id={ref.reference_telegram_id})")

            # Создаем текст с заголовком и общим счетом
            text = (
                       f"👥 *Ваши рефералы*\n"
                       f"📊 *Всего приглашено:* {total_referrals} человек\n"
                       f"📄 *Страница {page + 1}/{max_page + 1}*\n\n"
                   ) + '\n'.join(data)

            # Создаем клавиатуру с пагинацией
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

            keyboard = InlineKeyboardMarkup(row_width=3)

            # Кнопки пагинации
            row_buttons = []

            # Кнопка "Назад"
            if page > 0:
                row_buttons.append(InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=f"referral_list:{page - 1}"
                ))

            # Информация о странице
            row_buttons.append(InlineKeyboardButton(
                text=f"{page + 1}/{max_page + 1}",
                callback_data="no_action"
            ))

            # Кнопка "Вперед"
            if page < max_page:
                row_buttons.append(InlineKeyboardButton(
                    text="Вперед ▶️",
                    callback_data=f"referral_list:{page + 1}"
                ))

            if row_buttons:
                keyboard.row(*row_buttons)

            # Кнопка возврата в меню
            keyboard.row(
                InlineKeyboardButton(
                    text="🔙 Назад в меню",
                    callback_data="reference_menu"
                )
            )

            # Проверяем, есть ли уже сообщение с клавиатурой
            if call.message.text and "Ваши рефералы" in call.message.text:
                # Редактируем существующее сообщение
                await call.message.edit_text(
                    text=text,
                    parse_mode=types.ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            else:
                # Отправляем новое сообщение
                await call.message.reply(
                    text=text,
                    parse_mode=types.ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
        else:
            if total_referrals == 0:
                # Нет рефералов вообще
                await call.message.reply(
                    '👥 *Ваши рефералы*\n'
                    '📊 *Всего приглашено:* 0 человек\n\n'
                    'У вас пока нет рефералов. Приглашайте друзей по своей реферальной ссылке!',
                    parse_mode=types.ParseMode.MARKDOWN
                )
            else:
                # Есть рефералы, но на этой странице нет
                await call.message.reply(
                    '📄 Нет рефералов на этой странице.\n'
                    'Вернитесь на предыдущую страницу.',
                    parse_mode=types.ParseMode.MARKDOWN
                )

    except Exception as e:
        print(f"❌ Ошибка получения списка рефералов: {e}")
        await call.message.reply('❌ Ошибка при получении списка рефералов')
    finally:
        db.close()


async def no_action_call(call: types.CallbackQuery):
    """
    Пустой обработчик для кнопок, которые не должны ничего делать
    (например, кнопка с номером страницы)
    """
    await call.answer()  # Просто отвечаем на callback, но ничего не меняем


def register_reference_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(reference_menu_call, lambda call: call.data == "reference_menu")
    dp.register_callback_query_handler(reference_link_call, lambda call: call.data == "reference_link")

    # Регистрируем хендлер для списка рефералов с пагинацией
    # Он будет обрабатывать как "referral_list", так и "referral_list:0", "referral_list:1" и т.д.
    dp.register_callback_query_handler(
        reference_list_call,
        lambda call: call.data and (call.data == "referral_list" or call.data.startswith("referral_list:"))
    )

    # Регистрируем пустой обработчик для кнопок без действия
    dp.register_callback_query_handler(no_action_call, lambda call: call.data == "no_action")