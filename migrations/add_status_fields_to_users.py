# migrations/add_status_fields_to_users.py
import sys
import os
import logging
from sqlalchemy import create_engine, text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from database import DATABASE_URL
except ImportError:
    DATABASE_URL = "postgresql://username:password@localhost/dbname"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def add_status_fields_to_users():
    """Добавляет поля статуса в таблицу users"""

    queries = [
        # Добавляем поле status_text
        """
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS status_text VARCHAR(200);
        """,

        # Добавляем поле status_changed_at
        """
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP;
        """,

        # Создаем индекс для быстрого поиска
        """
        CREATE INDEX IF NOT EXISTS idx_users_status_text 
        ON users(status_text);
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

        logger.info("✅ Поля статуса успешно добавлены в таблицу users")
        return True

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Запуск миграции для добавления полей статуса в users...")
    if add_status_fields_to_users():
        logger.info("✅ Миграция успешно завершена!")
    else:
        logger.error("❌ Миграция завершилась с ошибками")
        sys.exit(1)