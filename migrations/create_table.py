# create_table.py
from sqlalchemy import text
from database import engine

sql_commands = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_chat_messages_user_id ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS ix_chat_messages_chat_id ON chat_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(chat_id, created_at);
"""

try:
    with engine.connect() as conn:
        # Проверяем, существует ли таблица
        result = conn.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'chat_messages')"))
        exists = result.scalar()

        if exists:
            print("✅ Таблица chat_messages уже существует")
        else:
            # Создаем таблицу
            for statement in sql_commands.split(';'):
                if statement.strip():
                    conn.execute(text(statement))
            conn.commit()
            print("✅ Таблица chat_messages создана")

except Exception as e:
    print(f"❌ Ошибка создания таблицы: {e}")