# admin_constants.py

# Конфигурация
ADMIN_IDS = [6090751674, 1054684037, 7268172384]
BROADCAST_BATCH_SIZE = 10
BROADCAST_DELAY = 0.1

# Константы для привилегий
PRIVILEGES = {
    "thief": {"id": 1, "name": "👑 Вор в законе", "extendable": True, "default_days": 30},
    "police": {"id": 2, "name": "👮‍♂️ Полицейский", "extendable": True, "default_days": 30},
    "unlimit": {"id": 3, "name": "🔐 Снятие лимита перевода", "extendable": False, "default_days": 0}
}

PROTECTIONS = {
    "search": {"id": 4, "name": "🛡️ Защита от поиска", "extendable": True},
    "stop": {"id": 5, "name": "🛡️ Защита от бот стоп", "extendable": True},
    "full": {"id": 6, "name": "🛡️ Полная защита (мут+стоп)", "extendable": True}
}

# Константы для предметов магазина
SHOP_ITEMS = {
    "unlimited_transfers": 3
}