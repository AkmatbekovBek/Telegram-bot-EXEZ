import psycopg2
from config import DATABASE_URL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_database():
    """Исправить проблемы с базой данных"""

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cursor = conn.cursor()

    try:
        logger.info("🔄 Исправление проблем с базой данных...")

        # 1. Изменить тип chat_id на BIGINT во всех таблицах
        tables = [
            'roulette_game_logs',
            'chat_messages',
            'roulette_settings',
            'user_purchases',
            'user_limits',
            'bot_ban_records',
            'marriage_records',
            'chat_activity_logs',
            'roulette_chat_sessions',
            'thief_logs',
            'police_logs',
            'race_logs'
        ]

        for table in tables:
            try:
                cursor.execute(f"""
                    ALTER TABLE {table} 
                    ALTER COLUMN chat_id TYPE BIGINT;
                """)
                logger.info(f"✅ Таблица {table}: chat_id изменен на BIGINT")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось изменить {table}: {e}")

        # 2. Добавить колонку game_session_id в roulette_transactions
        try:
            cursor.execute("""
                ALTER TABLE roulette_transactions 
                ADD COLUMN IF NOT EXISTS game_session_id INTEGER;
            """)
            logger.info("✅ Колонка game_session_id добавлена в roulette_transactions")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось добавить game_session_id: {e}")

        # 3. Создать таблицу roulette_game_logs если не существует
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roulette_game_logs (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                result INTEGER NOT NULL,
                color_emoji VARCHAR(10) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("✅ Таблица roulette_game_logs создана/проверена")

        logger.info("✅ Все проблемы с базой данных исправлены!")

    except Exception as e:
        logger.error(f"❌ Ошибка при исправлении БД: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    fix_database()