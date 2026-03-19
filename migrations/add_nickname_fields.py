# migrations/add_nickname_fields.py
import sys
import os
import logging
from sqlalchemy import create_engine, text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from database import DATABASE_URL
except ImportError:
    DATABASE_URL = "postgresql://username:password@localhost/dbname"  # ЗАМЕНИТЕ

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def add_nickname_fields():
    """Добавляет поля никнейма в таблицу telegram_users"""

    queries = [
        # Добавляем поле nickname
        """
        ALTER TABLE telegram_users 
        ADD COLUMN IF NOT EXISTS nickname VARCHAR(32);
        """,

        # Добавляем поле nickname_changed_at
        """
        ALTER TABLE telegram_users 
        ADD COLUMN IF NOT EXISTS nickname_changed_at TIMESTAMP WITH TIME ZONE;
        """,

        # Создаем уникальный индекс на nickname
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_users_nickname_unique 
        ON telegram_users(nickname) 
        WHERE nickname IS NOT NULL;
        """,

        # Создаем обычный индекс для поиска
        """
        CREATE INDEX IF NOT EXISTS idx_telegram_users_nickname 
        ON telegram_users(nickname);
        """
    ]

    engine = create_engine(DATABASE_URL)

    try:
        with engine.connect() as conn:
            for i, query in enumerate(queries, 1):
                logger.info(f"Выполняем запрос #{i}...")
                try:
                    conn.execute(text(query))
                    conn.commit()
                    logger.info(f"✅ Запрос #{i} выполнен")
                except Exception as e:
                    logger.warning(f"⚠️ Предупреждение при запросе #{i}: {e}")
                    conn.rollback()

        logger.info("✅ Поля никнейма успешно добавлены")
        return True

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Запуск миграции для добавления полей никнейма...")
    if add_nickname_fields():
        logger.info("✅ Миграция успешно завершена!")
    else:
        logger.error("❌ Миграция завершилась с ошибками")
        sys.exit(1)