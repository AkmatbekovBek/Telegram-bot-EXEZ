# check_status_fields.py
from database import SessionLocal
from sqlalchemy import inspect

db = SessionLocal()
inspector = inspect(db.get_bind())

# Проверяем таблицу telegram_users
columns = inspector.get_columns('telegram_users')
print("Поля в telegram_users:")
for col in columns:
    print(f"  - {col['name']}: {col['type']}")

db.close()