# check_table.py
from sqlalchemy import text
from database import engine

try:
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'chat_messages')"))
        exists = result.scalar()

        if exists:
            print("✅ Таблица chat_messages существует")

            # Проверяем структуру
            result = conn.execute(text("SELECT COUNT(*) FROM chat_messages"))
            count = result.scalar()
            print(f"📊 Количество записей в таблице: {count}")
        else:
            print("❌ Таблица chat_messages НЕ существует!")

except Exception as e:
    print(f"❌ Ошибка проверки таблицы: {e}")