# migrations/add_status_fields_to_all_tables.py
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


def add_status_fields_to_all_tables():
    """Добавляет поля статуса во все таблицы пользователей"""

    tables_to_update = [
        {
            'name': 'users',
            'status_text_type': 'VARCHAR(200)',
            'status_changed_at_type': 'TIMESTAMP'
        },
        {
            'name': 'telegram_users',
            'status_text_type': 'VARCHAR(200)',
            'status_changed_at_type': 'TIMESTAMP WITH TIME ZONE'
        }
    ]

    engine = create_engine(DATABASE_URL)

    try:
        with engine.connect() as conn:
            for table in tables_to_update:
                logger.info(f"🔧 Обновление таблицы {table['name']}...")

                # Добавляем status_text
                try:
                    query = f"""
                    ALTER TABLE {table['name']} 
                    ADD COLUMN IF NOT EXISTS status_text {table['status_text_type']};
                    """
                    conn.execute(text(query))
                    conn.commit()
                    logger.info(f"✅ Добавлен status_text в {table['name']}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось добавить status_text в {table['name']}: {e}")
                    conn.rollback()

                # Добавляем status_changed_at
                try:
                    query = f"""
                    ALTER TABLE {table['name']} 
                    ADD COLUMN IF NOT EXISTS status_changed_at {table['status_changed_at_type']};
                    """
                    conn.execute(text(query))
                    conn.commit()
                    logger.info(f"✅ Добавлен status_changed_at в {table['name']}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось добавить status_changed_at в {table['name']}: {e}")
                    conn.rollback()

                # Создаем индекс
                try:
                    query = f"""
                    CREATE INDEX IF NOT EXISTS idx_{table['name']}_status_text 
                    ON {table['name']}(status_text);
                    """
                    conn.execute(text(query))
                    conn.commit()
                    logger.info(f"✅ Создан индекс для {table['name']}.status_text")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось создать индекс для {table['name']}: {e}")
                    conn.rollback()

        logger.info("✅ Все таблицы обновлены!")
        return True

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Запуск миграции для добавления полей статуса во все таблицы...")
    if add_status_fields_to_all_tables():
        logger.info("✅ Миграция успешно завершена!")
    else:
        logger.error("❌ Миграция завершилась с ошибками")
        sys.exit(1)