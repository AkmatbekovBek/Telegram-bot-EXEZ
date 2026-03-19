# handlers/modroul/__init__.py

import logging

logger = logging.getLogger(__name__)

# Проверьте что эти файлы существуют:
from .bot_search_handler import BotSearchHandler, register_bot_search_handlers
from .bot_stop_handler import SimpleBotStopHandler, register_bot_stop_handlers
from .gifts import GiftHandlers, register_gift_handlers, ensure_gifts_on_startup
from .shop import ShopHandler, register_shop_handlers

# Реэкспорт основных функций
__all__ = [
    'BotSearchHandler',
    'SimpleBotStopHandler',
    'GiftHandlers',
    'ShopHandler',
    'register_all_handlers',
    'ensure_gifts_on_startup'
]


def register_all_handlers(dp):
    """Регистрация всех обработчиков модуля"""
    try:
        logger.info("🔄 Начинаем регистрацию modroul обработчиков...")

        # ПРОВЕРЬТЕ ЧТО ВСЕ ЭТИ ФУНКЦИИ СУЩЕСТВУЮТ
        register_bot_search_handlers(dp)
        logger.info("✅ bot_search зарегистрирован")

        register_bot_stop_handlers(dp)
        logger.info("✅ bot_stop зарегистрирован")

        register_gift_handlers(dp)
        logger.info("✅ gifts зарегистрирован")

        register_shop_handlers(dp)
        logger.info("✅ shop зарегистрирован")

        logger.info("✅ Все обработчики модуля modroul зарегистрированы")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка регистрации обработчиков modroul: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False