# handlers/donate/keyboards.py

from aiogram import types
from database.crud import DonateRepository
from .config import DONATE_ITEMS, SUPPORT_USERNAME, COIN_PACKAGES


def create_main_donate_keyboard():
    """Создает главную клавиатуру доната"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.row(
        types.InlineKeyboardButton(
            text="💎 Купить монеты",
            callback_data="donate_buy_coins_menu"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="👑 Привилегии",
            callback_data="donate_privileges"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="🎁 Бонус",
            callback_data="daily_bonus"
        )
    )

    # Кнопка назад в главное меню
    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад в меню",
            callback_data="back_to_main"
        )
    )

    return keyboard


def create_buy_coins_menu_keyboard():
    """Создает клавиатуру для выбора пакета монет"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    for package in COIN_PACKAGES:
        button_text = f"💎 {package['amount']:,}"
        callback_data = f"select_coins_{package['id']}"

        keyboard.insert(
            types.InlineKeyboardButton(
                text=button_text,
                callback_data=callback_data
            )
        )

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад в донат",
            callback_data="back_to_donate"
        ),
        types.InlineKeyboardButton(
            text="🏠 В меню",
            callback_data="back_to_main"
        )
    )

    return keyboard


def create_payment_method_keyboard(item_type, item_id):
    """Создает клавиатуру выбора метода оплаты (звезды + реквизиты)"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    if item_type == "coins":
        package = next((p for p in COIN_PACKAGES if p["id"] == item_id), None)
        if package and package['stars_price'] > 0:
            keyboard.row(
                types.InlineKeyboardButton(
                    text=f"⭐ Оплатить {package['stars_text']}",
                    callback_data=f"pay_stars_{item_type}_{item_id}"
                )
            )

    elif item_type == "privilege":
        item = next((i for i in DONATE_ITEMS if i["id"] == item_id), None)
        if item and item.get("stars_price", 0) > 0:
            keyboard.row(
                types.InlineKeyboardButton(
                    text=f"⭐ Оплатить {item['stars_text']}",
                    callback_data=f"pay_stars_{item_type}_{item_id}"
                )
            )

    # Ручная оплата по реквизитам (автодонат с чеком)
    keyboard.row(
        types.InlineKeyboardButton(
            text="🏦 Оплата по реквизитам (чек)",
            callback_data=f"pay_manual_{item_type}_{item_id}"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="💬 Написать в кассу (другие способы)",
            url=f"https://t.me/{SUPPORT_USERNAME}"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_buy" if item_type == "coins" else "donate_privileges"
        ),
        types.InlineKeyboardButton(
            text="🏠 В меню",
            callback_data="back_to_main"
        )
    )

    return keyboard


def create_privileges_keyboard(user_id: int = None):
    """Создает клавиатуру привилегий"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    # Проверяем активные покупки
    active_purchases = []
    if user_id:
        repo = DonateRepository()
        try:
            user_purchases = repo.get_user_active_purchases(user_id)
            active_purchases = [p.item_id for p in user_purchases]
        except Exception:
            active_purchases = []
        finally:
            if hasattr(repo, 'close'):
                repo.close()

    for item in DONATE_ITEMS:
        if item["id"] in active_purchases:
            # Уже куплено
            callback_data = f"donate_already_bought_{item['id']}"
            emoji = "✅"
            text = f"{emoji} {item['name']} (куплено)"
        else:
            # Можно купить
            callback_data = f"select_privilege_{item['id']}"
            emoji = item["name"].split()[0]
            text = f"{emoji} {item['name']}"

        keyboard.row(
            types.InlineKeyboardButton(
                text=text,
                callback_data=callback_data
            )
        )

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад в донат",
            callback_data="back_to_donate"
        ),
        types.InlineKeyboardButton(
            text="🏠 В меню",
            callback_data="back_to_main"
        )
    )

    return keyboard


def create_bonus_keyboard(is_available: bool):
    """Создает клавиатуру бонусов"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    if is_available:
        keyboard.row(
            types.InlineKeyboardButton(
                text="🎁 Получить бонус 50K",
                callback_data="claim_bonus"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                text="💎 Получить бонусы за привилегии",
                callback_data="claim_privilege_bonus"
            )
        )
    else:
        keyboard.row(
            types.InlineKeyboardButton(
                text="🎁 Бонус 50K",
                callback_data="daily_bonus_info"
            )
        )

        keyboard.row(
            types.InlineKeyboardButton(
                text="💎 Бонусы за привилегии",
                callback_data="privilege_bonus_info"
            )
        )

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад в донат",
            callback_data="back_to_donate"
        ),
        types.InlineKeyboardButton(
            text="🏠 В меню",
            callback_data="back_to_main"
        )
    )

    return keyboard


def create_back_keyboard():
    """Создает клавиатуру с кнопкой назад"""
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад в донат",
            callback_data="back_to_donate"
        ),
        types.InlineKeyboardButton(
            text="🏠 В меню",
            callback_data="back_to_main"
        )
    )

    return keyboard