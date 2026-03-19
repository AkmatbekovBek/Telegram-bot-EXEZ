# migrations/fix_user_chats_types.py
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


def fix_user_chats_types():
    """Исправляет типы данных в таблице user_chats"""

    queries = [
        # 1. Проверяем текущие типы
        """
        SELECT 
            column_name, 
            data_type, 
            numeric_precision
        FROM information_schema.columns 
        WHERE table_name = 'user_chats'
        ORDER BY ordinal_position;
        """,

        # 2. Изменяем chat_id на BIGINT
        """
        ALTER TABLE user_chats 
        ALTER COLUMN chat_id TYPE BIGINT;
        """,

        # 3. Изменяем user_id на BIGINT (если нужно)
        """
        ALTER TABLE user_chats 
        ALTER COLUMN user_id TYPE BIGINT;
        """
    ]

    engine = create_engine(DATABASE_URL)

    try:
        with engine.connect() as conn:
            # 1. Показываем текущую структуру
            logger.info("📊 Текущая структура таблицы user_chats:")
            result = conn.execute(text(queries[0]))
            for row in result:
                logger.info(f"  {row[0]}: {row[1]} (precision: {row[2]})")

            # 2. Исправляем chat_id
            logger.info("🛠️ Изменяем chat_id на BIGINT...")
            try:
                conn.execute(text(queries[1]))
                conn.commit()
                logger.info("✅ chat_id изменен на BIGINT")
            except Exception as e:
                logger.error(f"❌ Ошибка изменения chat_id: {e}")
                conn.rollback()

            # 3. Исправляем user_id
            logger.info("🛠️ Изменяем user_id на BIGINT...")
            try:
                conn.execute(text(queries[2]))
                conn.commit()
                logger.info("✅ user_id изменен на BIGINT")
            except Exception as e:
                logger.error(f"❌ Ошибка изменения user_id: {e}")
                conn.rollback()

        logger.info("✅ Типы данных исправлены!")
        return True

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Исправление типов данных в таблице user_chats...")
    if fix_user_chats_types():
        logger.info("✅ Исправление завершено успешно!")
    else:
        logger.error("❌ Исправление завершилось с ошибками")
        sys.exit(1)