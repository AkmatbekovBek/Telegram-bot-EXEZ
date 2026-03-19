# handlers/police/service.py
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from database import get_db
from database.crud import PoliceRepository, ShopRepository

logger = logging.getLogger(__name__)


class PoliceService:
    """Сервисный слой для логики полиции"""

    MAX_ARREST_MINUTES = 1440  # 24 часа
    MIN_ARREST_MINUTES = 1
    DEFAULT_ARREST_MINUTES = 180  # 3 часа
    POLICE_COOLDOWN_HOURS = 3
    POLICE_PRIVILEGE_ID = 2
    THIEF_PRIVILEGE_ID = 1

    @staticmethod
    def parse_arrest_time(text: str) -> int:
        """Парсит 'арест 1д 2ч 30м' → минуты (макс. 1440)"""
        try:
            text = text.lower()
            total = 0
            patterns = [
                (r'(\d+)\s*д[ень]*', 1440),
                (r'(\d+)\s*ч[ас]*', 60),
                (r'(\d+)\s*м[ин]*', 1),
            ]

            for pat, mult in patterns:
                for m in re.finditer(pat, text):
                    total += int(m.group(1)) * mult

            if total == 0:
                return PoliceService.DEFAULT_ARREST_MINUTES

            return max(
                PoliceService.MIN_ARREST_MINUTES,
                min(total, PoliceService.MAX_ARREST_MINUTES)
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга времени ареста: {e}")
            return PoliceService.DEFAULT_ARREST_MINUTES

    @staticmethod
    def check_police_permission(user_id: int) -> bool:
        """Проверяет права полицейского"""
        db = next(get_db())
        try:
            purchases = ShopRepository.get_user_purchases(db, user_id)
            has_permission = PoliceService.POLICE_PRIVILEGE_ID in purchases

            if has_permission:
                logger.info(f"✅ User {user_id} имеет права полицейского")
            else:
                logger.info(f"❌ User {user_id} не имеет прав полицейского")

            return has_permission
        except Exception as e:
            logger.error(f"Ошибка проверки прав полицейского: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def check_thief_permission(user_id: int) -> bool:
        """Проверяет права вора в законе"""
        db = next(get_db())
        try:
            purchases = ShopRepository.get_user_purchases(db, user_id)
            has_permission = PoliceService.THIEF_PRIVILEGE_ID in purchases

            if has_permission:
                logger.info(f"✅ User {user_id} имеет права вора")
            else:
                logger.info(f"❌ User {user_id} не имеет прав вора")

            return has_permission
        except Exception as e:
            logger.error(f"Ошибка проверки прав вора: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def check_police_cooldown(police_id: int) -> Tuple[bool, Optional[datetime]]:
        """Проверяет кулдаун полицейского"""
        db = next(get_db())
        try:
            last = PoliceRepository.get_last_arrest_by_police(db, police_id)
            if not last:
                logger.info(f"✅ Полицейский {police_id} не имеет предыдущих арестов")
                return True, None

            end = last.arrested_at + timedelta(hours=PoliceService.POLICE_COOLDOWN_HOURS)
            now = datetime.now()

            can_arrest = now >= end
            cooldown_end = end if not can_arrest else None

            if can_arrest:
                logger.info(f"✅ Полицейский {police_id} может арестовать")
            else:
                logger.info(f"⏳ Полицейский {police_id} на кулдауне до {cooldown_end}")

            return can_arrest, cooldown_end

        except Exception as e:
            logger.error(f"Ошибка проверки кулдауна: {e}")
            return True, None
        finally:
            db.close()

    @staticmethod
    def is_user_arrested(user_id: int) -> bool:
        """Проверяет, арестован ли пользователь"""
        db = next(get_db())
        try:
            arrest = PoliceRepository.get_user_arrest(db, user_id)
            if not arrest:
                return False

            if arrest.release_time <= datetime.now():
                PoliceRepository.unarrest_user(db, user_id)
                db.commit()
                return False

            return True

        except Exception as e:
            logger.error(f"Ошибка проверки ареста: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def arrest_user(police_id: int, thief_id: int, minutes: int) -> Tuple[bool, str]:
        """Выполняет арест пользователя"""
        db = next(get_db())
        try:
            # Проверяем, не арестован ли уже
            if PoliceService.is_user_arrested(thief_id):
                return False, "⚠️ Пользователь уже арестован!"

            # Выполняем арест
            release = datetime.now() + timedelta(minutes=minutes)
            PoliceRepository.arrest_user(db, thief_id, police_id, release)
            db.commit()

            logger.info(f"✅ Успешный арест: полицейский {police_id} -> вор {thief_id} на {minutes} минут")
            return True, f"✅ Арест на {minutes} мин"

        except Exception as e:
            db.rollback()
            logger.error(f"❌ Ошибка БД при аресте: {e}")
            return False, f"❌ Ошибка БД: {e}"
        finally:
            db.close()

    @staticmethod
    def _get_user_arrest_raw(db, user_id: int):
        """Получает запись об аресте без очистки (для check_arrest)"""
        from database.models import UserArrest
        try:
            return db.query(UserArrest).filter(UserArrest.user_id == user_id).first()
        except Exception as e:
            logger.error(f"Ошибка получения ареста: {e}")
            return None