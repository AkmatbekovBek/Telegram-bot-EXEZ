# main.py
import os
from dotenv import load_dotenv
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, \
    BotCommandScopeDefault

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

import asyncio
import logging
import signal
import sys
import inspect

from sqlalchemy import text
from aiogram import executor, Dispatcher
from aiogram.types import AllowedUpdates

from handlers.admin.mute_ban import register_handlers as register_mute_ban_handlers
from handlers.modroul.gifts import ensure_gifts_on_startup
from logging.handlers import RotatingFileHandler

from middlewares.auto_register_middleware import AutoRegisterMiddleware
from middlewares.bot_ban_middleware import BotBanMiddleware

from handlers.cleanup_scheduler import CleanupScheduler
from config import dp, bot
from database import engine, SessionLocal
from database.models import Base

from handlers.donate.handlers import register_donate_handlers

# Обновленный список обработчиков с правильными путями
HANDLERS = [
    ("start", "register_start_handler"),
    ("admin", "register_admin_handlers"),
    ("admin.user_data_display", "register_user_info_handlers"),  # ← ДОБАВЬТЕ ЭТУ СТРОЧКУ!
    ("invite_tracker", "register_invite_tracker_handlers"),
    ("donate", "register_donate_handlers"),
    ("callback", "register_callback_handlers"),
    ("reference", "register_reference_handlers"),
    ("transfer", "register_transfer_handlers"),
    ("history_service", "register_history_handlers"),
    ("record", "register_record_handlers"),
    ("marriage_handler", "register_marriage_handlers"),
    ("roulette", "register_roulette_handlers"),
    ("roulette.admin_commands", "register_roulette_admin_commands"),
    ("police", "register_police_handlers"),
    ("thief", "register_thief_handlers"),
    ("dice_game", "register_dice_handlers"),
    ("slot_machine", "register_slot_handlers"),
    ("raffle.raffle", "register_raffle_handlers"),
    ("mute_ban", "register_handlers"),
    ("modroul.bot_stop_handler", "register_bot_stop_handlers"),  # ВЫСОКИЙ ПРИОРИТЕТ: Блокировка ответов
    ("admin.cleanup_handler", "register_cleanup_handlers"),
    ("rock_paper_scissors.rock_paper_scissors", "register_rps_handlers"),
    ("chat_handlers", "register_chat_handlers"),
    ("aichat.ai_handler", "register_ai_handlers"),
    ("race.race", "register_race_handlers"),
    ("chat_activity", "register_chat_activity_handlers"),

]


# Модули в папке modroul (поиск, магазин, подарки и т.д.)
MODROUL_HANDLERS = [
    ("modroul.gifts", "register_gift_handlers"),
    ("modroul.shop", "register_shop_handlers"),
    ("modroul.bot_search_handler", "register_bot_search_handlers"),
]

# Настройка логирования
handlers = [logging.StreamHandler()]
try:
    handlers.append(
        RotatingFileHandler(
            "bot.log",
            maxBytes=5_000_000,
            backupCount=3,
            encoding="utf-8",
            delay=True
        )
    )
except Exception:
    # если файл нельзя открыть — работаем только в консоль
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s",
    handlers=handlers
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Временно для отладки

# Глобальные переменные
cleanup_scheduler = None
donate_scheduler = None


def setup_database() -> bool:
    """Настройка базы данных (синхронная)"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Все таблицы базы данных созданы")

        db = SessionLocal()
        try:
            db.expire_all()
            db.execute(text("SELECT 1"))
            db.commit()
            logger.info("✅ Подключение к базе данных установлено")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Ошибка проверки подключения к БД: {e}", exc_info=True)
            return False
        finally:
            db.close()

    except Exception as e:
        logger.error(f"❌ Ошибка настройки БД: {e}", exc_info=True)
        return False


def ensure_columns_exist() -> None:
    """
    Мини-миграции без Alembic:
    добавляем win_games / lose_games, если их нет.
    """
    try:
        db = SessionLocal()
        try:
            db.execute(text("ALTER TABLE telegram_users ADD COLUMN IF NOT EXISTS win_games INTEGER NOT NULL DEFAULT 0;"))
            db.execute(text("ALTER TABLE telegram_users ADD COLUMN IF NOT EXISTS lose_games INTEGER NOT NULL DEFAULT 0;"))
            db.commit()
            logger.info("✅ Проверка/добавление колонок win_games/lose_games выполнена")
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Ошибка автодобавления колонок win_games/lose_games: {e}", exc_info=True)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации ensure_columns_exist: {e}", exc_info=True)


def cleanup_old_limits() -> None:
    """Очистка старых записей лимитов (синхронная)"""
    try:
        from database.crud import TransferLimitRepository

        db = SessionLocal()
        try:
            db.expire_all()
            deleted_count = TransferLimitRepository.clean_old_transfers(db)
            if deleted_count > 0:
                logger.info(f"✅ Очищено {deleted_count} старых записей лимитов")
            else:
                logger.info("✅ Старые записи лимитов не найдены")
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке лимитов: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации очистки лимитов: {e}", exc_info=True)


def _call_register(register_func, dp_obj, bot_obj):
    """
    Универсальный вызов register_*:
    - если функция принимает 2+ параметра -> передаем (dp, bot)
    - иначе -> (dp)
    """
    try:
        sig = inspect.signature(register_func)
        params = list(sig.parameters.values())

        # Если первый параметр есть, а второй тоже ожидается без значения по умолчанию —
        # почти наверняка нужен bot.
        if len(params) >= 2:
            return register_func(dp_obj, bot_obj)
        return register_func(dp_obj)

    except TypeError:
        # Если signature не прочиталась — пробуем стандартно,
        # потом fallback с bot
        try:
            return register_func(dp_obj)
        except TypeError:
            return register_func(dp_obj, bot_obj)


def register_all_handlers():
    """
    Регистрация всех обработчиков.
    Возвращает mute_ban_manager (или None) для middleware.
    """
    logger.info("📝 Регистрация обработчиков...")

    registered_handlers = set()
    mute_ban_manager = None

    # 1. Сначала регистрируем основные HANDLERS
    for module_name, register_func_name in HANDLERS:
        try:
            if module_name == "mute_ban":
                mute_ban_manager = register_mute_ban_handlers(dp)
                logger.info("✅ mute_ban обработчики зарегистрированы")
                registered_handlers.add(module_name)
                continue

            module = __import__(f"handlers.{module_name}", fromlist=[register_func_name])
            register_func = getattr(module, register_func_name)

            _call_register(register_func, dp, bot)

            registered_handlers.add(module_name)
            logger.info(f"✅ {module_name} обработчики зарегистрированы")

        except (ImportError, AttributeError) as e:
            logger.error(f"❌ Ошибка регистрации {module_name}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при регистрации {module_name}: {e}", exc_info=True)

    # 2. Затем регистрируем MODROUL_HANDLERS
    for module_name, register_func_name in MODROUL_HANDLERS:
        try:
            module = __import__(f"handlers.{module_name}", fromlist=[register_func_name])
            register_func = getattr(module, register_func_name)

            _call_register(register_func, dp, bot)

            registered_handlers.add(module_name)
            logger.info(f"✅ {module_name} обработчики зарегистрированы")

        except (ImportError, AttributeError) as e:
            logger.error(f"❌ Ошибка регистрации {module_name}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при регистрации {module_name}: {e}", exc_info=True)

    logger.info(f"✅ Все обработчики зарегистрированы. Всего: {len(registered_handlers)}")
    return mute_ban_manager

async def start_cleanup_tasks(mute_ban_manager):
    """Запуск задач очистки и проверки банов"""
    try:
        global cleanup_scheduler
        cleanup_scheduler = CleanupScheduler()
        asyncio.create_task(cleanup_scheduler.start_daily_cleanup())
        logger.info("✅ Планировщик очистки БД запущен")

        if mute_ban_manager:
            mute_ban_manager.start_cleanup_tasks()
            logger.info("✅ Задачи проверки мутов/банов запущены")

            try:
                await mute_ban_manager.restore_mutes_after_restart()
                logger.info("✅ Активные муты восстановлены после перезапуска")
            except Exception as e:
                logger.error(f"❌ Ошибка восстановления мутов: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"❌ Ошибка запуска задач очистки: {e}", exc_info=True)
        raise


async def start_donate_scheduler():
    """Запуск планировщика донат-задач"""
    try:
        from handlers.donate.scheduler import DonateScheduler

        global donate_scheduler
        donate_scheduler = DonateScheduler(dp.bot)
        asyncio.create_task(donate_scheduler.start_scheduler())
        logger.info("✅ Планировщик донат-задач запущен")

    except ImportError as e:
        logger.error(f"❌ Ошибка импорта DonateScheduler: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска планировщика донат-задач: {e}", exc_info=True)


async def stop_donate_scheduler():
    """Остановка планировщика донат-задач"""
    global donate_scheduler
    if donate_scheduler:
        try:
            await donate_scheduler.stop_scheduler()
            logger.info("✅ Планировщик донат-задач остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки планировщика донат-задач: {e}", exc_info=True)


async def set_bot_commands():
    commands = [
        BotCommand("start", "создать профиль"),
        BotCommand("roulette", "рулетка"),
        BotCommand("shop", "подарки и бонусы"),
        BotCommand("top", "рейтинг участников чата"),
        BotCommand("record", "рекорды дня"),
        BotCommand("aioff", "отключить ИИ"),
        BotCommand("aion", "включить ИИ"),
        BotCommand("mymembers", "счет приглашенных"),
        BotCommand("my", "счет приглашенных"),
        BotCommand("donate", "донат"),
        BotCommand("clear_exez", "сбросить приглашения"),
        BotCommand("find_chats", "активные группы"),

    ]

    try:
        # 1) дефолт (если клиент/группа игнорит scope — это спасает)
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

        # 2) личка
        await bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())

        # 3) все группы (group + supergroup)
        await bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())

        logger.info("✅ Commands set: default + private + all groups")
    except Exception as e:
        logger.error(f"❌ set_my_commands ERROR: {e}", exc_info=True)



async def on_startup(_):
    """Действия при запуске бота"""
    logger.info("🚀 Запуск бота...")
    dp.middleware.setup(AutoRegisterMiddleware())

    # ✅ Команды бота (обязательно)
    await set_bot_commands()
    logger.info("✅ Команды бота установлены (all groups + private)")

    logger.info("📊 Настройка базы данных...")
    if not setup_database():
        raise RuntimeError("Не удалось настроить базу данных")

    # ✅ Авто-добавление нужных колонок (win_games/lose_games)
    ensure_columns_exist()

    logger.info("🧹 Очистка старых данных...")
    cleanup_old_limits()

    # ✅ Регистрируем обработчики ОДИН раз
    mute_ban_manager = register_all_handlers()

    # BotBanMiddleware
    if mute_ban_manager:
        if getattr(mute_ban_manager, "bot", None) is None and dp.bot:
            try:
                mute_ban_manager.set_bot(dp.bot)
                logger.info("✅ Бот установлен в MuteBanManager")
            except Exception:
                pass

        bot_ban_middleware = BotBanMiddleware(mute_ban_manager)
        dp.middleware.setup(bot_ban_middleware)

        try:
            mute_ban_manager.bot_ban_manager.set_middleware(bot_ban_middleware)
        except Exception:
            pass

        logger.info("✅ BotBanMiddleware зарегистрирован и связан с менеджером")

        try:
            await mute_ban_manager.bot_ban_manager.restore_bans_after_restart()
            logger.info("✅ Баны восстановлены после перезапуска")
        except Exception as e:
            logger.error(f"❌ Ошибка восстановления банов: {e}", exc_info=True)
    else:
        logger.warning("⚠️ BotBanMiddleware не зарегистрирован - mute_ban_manager не найден")

    # Подарки
    await ensure_gifts_on_startup()

    # Задачи очистки
    logger.info("⏰ Запуск задач очистки...")
    await start_cleanup_tasks(mute_ban_manager)

    # Донат-планировщик
    logger.info("💰 Запуск планировщика донат-задач...")
    await start_donate_scheduler()

    # --- ВОЗВРАТ СРЕДСТВ ЗА ЗАВИСШИЕ СТАВКИ ---
    try:
        from handlers.roulette.handlers import RouletteHandler
        await RouletteHandler.refund_active_bets_on_startup()
    except Exception as e:
        logger.error(f"❌ Ошибка запуска возврата средств: {e}")
    # ------------------------------------------

    # --- ЗАГРУЗКА АКТИВНЫХ РОЗЫГРЫШЕЙ ---
    try:
        from handlers.raffle.raffle import load_active_raffles_from_db
        load_active_raffles_from_db(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки розыгрышей: {e}")
    # ------------------------------------

    logger.info("✅ Бот успешно запущен")


async def on_shutdown(dp: Dispatcher):
    """Корректное завершение работы"""
    logger.info("🛑 Завершение работы бота...")

    try:
        global cleanup_scheduler
        if cleanup_scheduler:
            try:
                await cleanup_scheduler.stop()
                logger.info("✅ Планировщик очистки остановлен")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки планировщика: {e}", exc_info=True)

        await stop_donate_scheduler()

        try:
            from database import engine as _engine
            _engine.dispose()
            logger.info("✅ Соединения с БД закрыты")
        except Exception as e:
            logger.error(f"❌ Ошибка закрытия БД: {e}", exc_info=True)

        try:
            await dp.storage.close()
            await dp.storage.wait_closed()
            logger.info("✅ Хранилище диспетчера закрыто")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка закрытия хранилища: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"💥 Критическая ошибка при завершении: {e}", exc_info=True)
    finally:
        logger.info("✅ Бот остановлен")


def main():
    """Основная функция запуска бота"""

    def signal_handler(signum, frame):
        logger.info(f"📞 Получен сигнал {signum}. Завершение работы...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info("🔄 Запуск бота")

        executor.start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            timeout=60,
            allowed_updates=AllowedUpdates.all(),
            relax=0.5
        )

    except KeyboardInterrupt:
        logger.info("⏹️ Остановка по запросу пользователя")
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
