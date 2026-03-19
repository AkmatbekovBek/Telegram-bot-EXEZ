# keyboards/reference_keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def reference_menu_keyboard():
    """
    Клавиатура для меню рефералов
    """
    keyboard = InlineKeyboardMarkup(row_width=2)

    keyboard.row(
        InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="reference_link"),
        InlineKeyboardButton(text="👥 Список рефералов", callback_data="referral_list:0")
        # Изменено с "referral_list" на "referral_list:0"
    )

    keyboard.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")
    )

    return keyboard