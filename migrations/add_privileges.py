# migration/add_privileges.py

from database import SessionLocal
from database.crud import PrivilegeRepository, ShopRepository
from datetime import datetime, timedelta
import pytz


def migrate_existing_privileges():
    """Мигрирует существующие привилегии из ShopRepository в PrivilegeRepository"""
    db = SessionLocal()
    try:
        # Получаем всех пользователей
        from database.models import User
        users = db.query(User).all()

        migrated_count = 0

        for user in users:
            # Получаем текущие покупки
            purchases = ShopRepository.get_user_purchases(db, user.telegram_id)

            # Для каждой привилегии создаем запись
            now = datetime.now(pytz.UTC)
            expires_at = now + timedelta(days=28)

            if 1 in purchases:  # Вор
                PrivilegeRepository.add_privilege(db, user.telegram_id, 1)
                migrated_count += 1

            if 2 in purchases:  # Полицейский
                PrivilegeRepository.add_privilege(db, user.telegram_id, 2)
                migrated_count += 1

        db.commit()
        print(f"✅ Мигрировано {migrated_count} привилегий для {len(users)} пользователей")

    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка миграции: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    migrate_existing_privileges()