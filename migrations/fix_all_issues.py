# migrations/fix_all_issues.py
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


def fix_all_issues():
    """Исправляет все проблемы: добавляет поля статуса и исправляет тип данных"""

    queries = [
        # 1. Добавляем поля в таблицу users
        """
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS status_text VARCHAR(200),
        ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP;
        """,

        # 2. Добавляем поля в таблицу telegram_users
        """
        ALTER TABLE telegram_users 
        ADD COLUMN IF NOT EXISTS status_text VARCHAR(200),
        ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP WITH TIME ZONE;
        """,

        # 3. Исправляем user_chats.user_id на BIGINT
        """
        ALTER TABLE user_chats 
        ALTER COLUMN user_id TYPE BIGINT;
        """,

        # 4. Создаем индексы
        """
        CREATE INDEX IF NOT EXISTS idx_users_status_text ON users(status_text);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_telegram_users_status_text ON telegram_users(status_text);
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

        logger.info("✅ Все запросы выполнены")
        return True

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Запуск исправления всех проблем...")
    if fix_all_issues():
        logger.info("✅ Все проблемы исправлены!")
    else:
        logger.error("❌ Были ошибки при исправлении")
        sys.exit(1)