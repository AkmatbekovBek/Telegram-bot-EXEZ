import psycopg2
from config import DATABASE_URL
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def upgrade():
    op.add_column('marriages', sa.Column('chat_id', sa.BigInteger(), nullable=True))


def fix_all_tables():
    """Исправить все проблемы с типами данных в базе"""

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cursor = conn.cursor()

    try:
        logger.info("🔄 Исправление ВСЕХ таблиц с BIGINT...")

        # Список ВСЕХ таблиц и колонок, которые нужно исправить
        tables_and_columns = [
            # Таблица - Колонка
            ('roulette_game_logs', 'chat_id'),
            ('chat_messages', 'chat_id'),
            ('roulette_settings', 'chat_id'),
            ('user_purchases', 'chat_id'),
            ('user_limits', 'chat_id'),
            ('bot_ban_records', 'chat_id'),
            ('marriage_records', 'chat_id'),
            ('chat_activity_logs', 'chat_id'),
            ('roulette_chat_sessions', 'chat_id'),
            ('thief_logs', 'chat_id'),
            ('police_logs', 'chat_id'),
            ('race_logs', 'chat_id'),
            ('raffle_participants', 'chat_id'),

            # Таблицы с user_id (телеграм ID часто > 2^31)
            ('transfer_limits', 'user_id'),
            ('telegram_users', 'telegram_id'),
            ('user_references', 'referrer_telegram_id'),
            ('user_references', 'referred_telegram_id'),
            ('roulette_transactions', 'user_id'),
            ('thief_logs', 'user_id'),
            ('thief_logs', 'target_id'),
            ('police_logs', 'user_id'),
            ('police_logs', 'target_id'),
            ('marriage_records', 'user1_id'),
            ('marriage_records', 'user2_id'),
            ('user_purchases', 'user_id'),
            ('user_bonuses', 'user_id'),
            ('bot_ban_records', 'user_id'),
            ('user_limits', 'user_id'),
            ('race_logs', 'user_id'),
            ('raffle_participants', 'user_id'),
            ('chat_activity_logs', 'user_id'),
            ('donate_transactions', 'user_id'),
            ('subscription_checks', 'user_id'),
            ('user_statuses', 'user_id'),
            ('message_stats', 'user_id'),
            ('admin_users', 'telegram_id'),
        ]

        # Исправляем каждую колонку
        for table, column in tables_and_columns:
            try:
                # Проверяем существует ли таблица и колонка
                cursor.execute(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table}' 
                    AND column_name = '{column}'
                """)

                if cursor.fetchone():
                    # Изменяем тип на BIGINT
                    cursor.execute(f"""
                        ALTER TABLE {table} 
                        ALTER COLUMN {column} TYPE BIGINT;
                    """)
                    logger.info(f"✅ Таблица {table}.{column} изменен на BIGINT")
                else:
                    logger.warning(f"⚠️ Колонка {table}.{column} не существует, пропускаем")

            except Exception as e:
                logger.warning(f"⚠️ Не удалось изменить {table}.{column}: {e}")

        # 2. Добавить недостающие колонки
        additional_fixes = [
            # Добавить game_session_id в roulette_transactions если нет
            ("ALTER TABLE roulette_transactions ADD COLUMN IF NOT EXISTS game_session_id INTEGER;",
             "game_session_id в roulette_transactions"),

            # Создать таблицу transfer_limits если не существует
            ("""
            CREATE TABLE IF NOT EXISTS transfer_limits (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount BIGINT NOT NULL,
                transfer_time TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """, "таблица transfer_limits"),

            # Создать индекс для ускорения запросов
            ("CREATE INDEX IF NOT EXISTS idx_transfer_limits_user_time ON transfer_limits(user_id, transfer_time);",
             "индекс для transfer_limits"),
        ]

        for sql, description in additional_fixes:
            try:
                cursor.execute(sql)
                logger.info(f"✅ {description} создана/проверена")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось создать {description}: {e}")

        logger.info("✅ ВСЕ таблицы исправлены!")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при исправлении БД: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    fix_all_tables()