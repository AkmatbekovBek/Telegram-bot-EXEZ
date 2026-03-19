# handlers/donate/config.py

import logging
import os
from enum import Enum

# Конфигурация бонусов
BONUS_AMOUNT = 50000
BONUS_COOLDOWN_HOURS = 24
THIEF_BONUS_AMOUNT = 100000
POLICE_BONUS_AMOUNT = 50000
PRIVILEGE_BONUS_COOLDOWN_HOURS = 24
SUPPORT_USERNAME = "EXEZ_Kassa"

class BonusType(Enum):
    DAILY = "daily"
    THIEF = "thief"
    POLICE = "police"

# Конфигурация донат-товаров
DONATE_ITEMS = [
    {
        "id": 1,
        "name": "👑 Вор в законе",
        "price": "3000₽",
        "tenge_price": "19500 тенге",
        "stars_price": 1820,
        "stars_text": "1820 звезд",
        "duration": "30 дней",
        "description": "👑 Вор в законе",
        "benefit": "🎯 Можете красть монеты у других игроков!💰 Ежедневный бонус: 100,000 монет"
    },
    {
        "id": 2,
        "name": "👮‍♂️ Полицейский",
        "price": "1500₽",
        "tenge_price": "9800 тенге",
        "stars_price": 970,
        "stars_text": "970 звезд",
        "duration": "30 дней",
        "description": "👮‍♂️ Полицейский",
        "benefit": "⚖️ Можете арестовывать воров!💰 Ежедневный бонус: 50,000 монет"
    },
    {
        "id": 3,
        "name": "🔐 Снятие лимита перевода",
        "price": "100₽",
        "tenge_price": "680",
        "stars_price": 570,
        "stars_text": "570 звезд",
        "duration": "навсегда",
        "description": "🔐 Снятие лимита перевода",
        "benefit": "💸 Можете переводить неограниченные суммы!"
    }
]

# Конфигурация пакетов монет
COIN_PACKAGES = [
    {"id": 1, "amount": 250_000, "rub_price": 100, "tenge_price": 650, "stars_price": 80, "stars_text": "80 звезд"},
    {"id": 2, "amount": 600_000, "rub_price": 200, "tenge_price": 1300, "stars_price": 160, "stars_text": "160 звезд"},
    {"id": 3, "amount": 1_300_000, "rub_price": 400, "tenge_price": 2600, "stars_price": 320, "stars_text": "320 звезд"},
    {"id": 4, "amount": 2_800_000, "rub_price": 700, "tenge_price": 4550, "stars_price": 480, "stars_text": "480 звезд"},
    {"id": 5, "amount": 6_000_000, "rub_price": 1200, "tenge_price": 7800, "stars_price": 830, "stars_text": "830 звезд"},
    {"id": 6, "amount": 14_000_000, "rub_price": 2000, "tenge_price": 13000, "stars_price": 1250, "stars_text": "1250 звезд"},
    {"id": 7, "amount": 28_000_000, "rub_price": 3500, "tenge_price": 22800, "stars_price": 2000, "stars_text": "2000 звезд"},
    {"id": 8, "amount": 60_000_000, "rub_price": 6000, "tenge_price": 39150, "stars_price": 3800, "stars_text": "3800 звезд"},
    {"id": 9, "amount": 110_000_000, "rub_price": 7500, "tenge_price": 49000, "stars_price": 4500, "stars_text": "4500 звезд"},
]



AMMERPAY_TOKEN = "6073714100:TEST:TG_wJcHNzd6ZyFz9B1ItjRQUyIA"
AMMERPAY_TEST_MODE = True
AMMERPAY_PROVIDER_TOKEN = AMMERPAY_TOKEN  # Просто алиас

CHANNEL_USERNAME = "EXEZ_NEWS"
CHANNEL_LINK = "https://t.me/EXEZ_NEWS"
SUBSCRIPTION_BONUS_AMOUNT = 500  # Количество монет за подписку
SUBSCRIPTION_CHECK_COOLDOWN = 60  # 1 час между проверками

# --- Ручная оплата по реквизитам (автодонат с чеком) ---
# ВАЖНО: укажите ID супергруппы/группы админов, куда бот будет пересылать чеки.
# Для супергрупп Telegram ID выглядит как -100XXXXXXXXXX
DONATE_ADMIN_GROUP_ID = int(os.getenv("DONATE_ADMIN_GROUP_ID", "-4926758271"))

# Реквизиты для оплаты. Можно переопределить через переменную окружения.
# Совет: для многострочного текста используйте \n.
DONATE_PAYMENT_REQUISITES_TEXT = os.getenv(
    "DONATE_PAYMENT_REQUISITES_TEXT",
    """
<b>Реквизиты для оплаты</b>\n
• Банк: ...\n
• Карта: ...\n
• Получатель: ...\n
• Комментарий к переводу: <code>DONATE {user_id}</code>\n
""".strip(),
)

print("CONFIG LOAD DONATE_ADMIN_GROUP_ID =", DONATE_ADMIN_GROUP_ID)


logger = logging.getLogger(__name__)