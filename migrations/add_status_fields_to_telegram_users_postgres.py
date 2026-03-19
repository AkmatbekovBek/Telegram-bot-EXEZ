#!/usr/bin/env python3
"""
Скрипт для добавления полей статуса в таблицу telegram_users (PostgreSQL)
"""

import sys
import os
import logging
from sqlalchemy import create_engine, text

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем настройки БД
try:
    from database import DATABASE_URL
except ImportError:
    # Или укажите URL БД вручную
    DATABASE_URL = "postgresql://username:password@localhost/dbname"  # ЗАМЕНИТЕ НА СВОЙ

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def add_status_fields():
    """Добавляет поля статуса в таблицу telegram_users"""

    # SQL запросы для PostgreSQL
    queries = [
        # Добавляем столбец status_text
        """
        ALTER TABLE telegram_users 
        ADD COLUMN IF NOT EXISTS status_text VARCHAR(200);
        """,

        # Добавляем столбец status_changed_at
        """
        ALTER TABLE telegram_users 
        ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP WITH TIME ZONE;
        """,

        # Создаем индекс для быстрого поиска
        """
        CREATE INDEX IF NOT EXISTS idx_telegram_users_status_text 
        ON telegram_users(status_text);
        """
    ]

    try:
        # Создаем подключение
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Выполняем все запросы
            for i, query in enumerate(queries, 1):
                logger.info(f"Выполняем запрос #{i}...")
                logger.debug(f"SQL: {query.strip()}")

                try:
                    conn.execute(text(query))
                    conn.commit()
                    logger.info(f"✅ Запрос #{i} выполнен успешно")
                except Exception as e:
                    logger.error(f"❌ Ошибка при выполнении запроса #{i}: {e}")
                    # Продолжаем выполнение других запросов
                    conn.rollback()
                    continue

        logger.info("✅ Все запросы выполнены")
        return True

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False


def check_table_structure():
    """Проверяет структуру таблицы telegram_users"""

    check_query = """
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'telegram_users'
    ORDER BY ordinal_position;
    """

    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            result = conn.execute(text(check_query))
            columns = result.fetchall()

            logger.info("📊 Структура таблицы telegram_users:")
            logger.info("=" * 60)
            for col in columns:
                logger.info(f"{col[0]:30} {col[1]:20} {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
            logger.info("=" * 60)

            # Проверяем наличие нужных полей
            column_names = [col[0] for col in columns]

            if 'status_text' in column_names and 'status_changed_at' in column_names:
                logger.info("✅ Поля status_text и status_changed_at присутствуют в таблице")
                return True
            else:
                missing = []
                if 'status_text' not in column_names:
                    missing.append('status_text')
                if 'status_changed_at' not in column_names:
                    missing.append('status_changed_at')
                logger.warning(f"⚠️ Отсутствующие поля: {', '.join(missing)}")
                return False

    except Exception as e:
        logger.error(f"❌ Ошибка проверки структуры: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Запуск миграции для добавления полей статуса...")

    # Проверяем текущую структуру
    logger.info("🔍 Проверяем текущую структуру таблицы...")
    check_table_structure()

    # Добавляем поля
    logger.info("🛠️ Добавляем поля в таблицу...")
    if add_status_fields():
        logger.info("✅ Миграция успешно завершена")

        # Проверяем результат
        logger.info("🔍 Проверяем результат...")
        check_table_structure()
    else:
        logger.error("❌ Миграция завершилась с ошибками")
        sys.exit(1)