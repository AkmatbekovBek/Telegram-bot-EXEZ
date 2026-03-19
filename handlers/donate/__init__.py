# handlers/donate/__init__.py

import logging

# Импортируем все необходимые модули
from .handlers import DonateHandler, register_donate_handlers
from .texts_simple import donate_texts
from .scheduler import DonateScheduler
from .bonus import BonusManager, SubscriptionManager

logger = logging.getLogger(__name__)

# Глобальная переменная для планировщика
donate_scheduler = None

# Компоненты для экспорта
__all__ = [
    "DonateHandler",
    "register_donate_handlers",
    "donate_texts",
    "donate_scheduler",
    "start_donate_scheduler",
    "stop_donate_scheduler",
    "BonusManager",
    "SubscriptionManager"
]


async def setup_donate_module(dp, bot):
    """Настройка всего модуля доната"""
    try:
        # Регистрируем основные хендлеры доната
        register_donate_handlers(dp, bot)

        # Регистрируем хендлеры подписки и бонусов
        try:
            from .subscription_handler import register_subscription_handlers
            register_subscription_handlers(dp)
            logger.info("✅ Хендлеры подписки и бонусов зарегистрированы")
        except ImportError as e:
            logger.error(f"❌ Ошибка импорта хендлеров подписки: {e}")

        logger.info("✅ Модуль доната успешно настроен")

    except Exception as e:
        logger.error(f"❌ Ошибка настройки модуля доната: {e}")


async def start_donate_scheduler(bot):
    """Запускает планировщик доната"""
    global donate_scheduler
    try:
        donate_scheduler = DonateScheduler(bot)
        await donate_scheduler.start_scheduler()
        logger.info("✅ Планировщик доната запущен")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска планировщика доната: {e}")


async def stop_donate_scheduler():
    """Останавливает планировщик доната"""
    global donate_scheduler
    try:
        if donate_scheduler:
            await donate_scheduler.stop_scheduler()
            logger.info("✅ Планировщик доната остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка остановки планировщика доната: {e}")