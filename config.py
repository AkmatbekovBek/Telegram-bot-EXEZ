from decouple import config
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os

DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Хранилище состояний
storage = MemoryStorage()

# Получаем токен из .env
TGBOTtoken: str = config("TGBOTtoken", default=None)
DATABASE_URL = config("DATABASE_URL")

if not TGBOTtoken:
    raise ValueError("❌ Токен бота не найден! Добавь TGBOTtoken в .env файл.")

# Инициализация бота и диспетчера
bot = Bot(token=TGBOTtoken, parse_mode="HTML")
dp = Dispatcher(bot=bot, storage=storage)
