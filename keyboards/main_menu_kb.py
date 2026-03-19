# keyboards/main_menu_kb.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_inline_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Первый ряд
    keyboard.add(
        InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        InlineKeyboardButton("🎰 Рулетка", callback_data="roulette")
    )

    # Второй ряд
    keyboard.add(
        InlineKeyboardButton("🔗 Ссылки", callback_data="links"),
        InlineKeyboardButton("👥 Рефералы", callback_data="reference")
    )

    # Третий ряд
    keyboard.add(
        InlineKeyboardButton("🛍️ Магазин", callback_data="shop"),
        InlineKeyboardButton("🎁 Подарки", callback_data="gifts")
    )

    # Четвертый ряд
    keyboard.add(
        InlineKeyboardButton("🤖 Другие боты", callback_data="other_bots"),
        InlineKeyboardButton("💎 Донат", callback_data="donate")
    )

    # Пятый ряд - FAQ кнопка (в новом ряду для лучшей видимости)
    keyboard.add(
        InlineKeyboardButton("📚 FAQ", url="https://telegra.ph/EXEZ-01-20")
    )

    # Шестой ряд
    keyboard.add(
        InlineKeyboardButton("🛠️ Тех. поддержка", callback_data="support")
    )

    # Седьмой ряд
    keyboard.add(
        InlineKeyboardButton("📄 Пользовательское соглашение", callback_data="agreement")
    )

    return keyboard


def back_to_main_keyboard():
    """Клавиатура только с кнопкой 'Назад'"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_main")
    )
    return keyboard