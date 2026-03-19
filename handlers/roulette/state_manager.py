# handlers/roulette/state_manager.py
import logging
from typing import Dict, Set, Optional
from datetime import datetime
import json
import os

logger = logging.getLogger(__name__)

# Файл для сохранения состояний
STATE_FILE = "roulette_states.json"


class RouletteStateManager:
    """Менеджер состояния рулетки по чатам"""

    def __init__(self):
        self.chat_states = self._load_states()
        self._admins_cache: Dict[int, bool] = {}
        self._cache_expiry: Dict[int, float] = {}

    def _load_states(self) -> Dict[int, bool]:
        """Загружает состояния из файла"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Конвертируем ключи из строк в int
                    return {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error(f"Ошибка загрузки состояний рулетки: {e}")
        return {}

    def _save_states(self):
        """Сохраняет состояния в файл"""
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.chat_states, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения состояний рулетки: {e}")

    def is_roulette_enabled(self, chat_id: int) -> bool:
        """Проверяет, включена ли рулетка в чате"""
        # По умолчанию рулетка включена во всех чатах
        return self.chat_states.get(chat_id, True)

    def enable_roulette(self, chat_id: int):
        """Включает рулетку в чате"""
        self.chat_states[chat_id] = True
        self._save_states()
        logger.info(f"Рулетка включена в чате {chat_id}")

    def disable_roulette(self, chat_id: int):
        """Отключает рулетку в чате"""
        self.chat_states[chat_id] = False
        self._save_states()
        logger.info(f"Рулетка отключена в чате {chat_id}")

    async def check_admin_permissions(self, user_id: int, chat_id: int, bot) -> bool:
        """Проверяет, является ли пользователь администратором группы или бота"""

        # Проверка кэша (срок действия 5 минут)
        current_time = datetime.now().timestamp()
        cache_key = f"{user_id}_{chat_id}"

        if cache_key in self._admins_cache:
            if current_time - self._cache_expiry.get(cache_key, 0) < 300:  # 5 минут
                return self._admins_cache[cache_key]

        try:
            # Проверяем права в группе (если это не ЛС)
            if chat_id != user_id:  # Если не личные сообщения
                try:
                    chat_member = await bot.get_chat_member(chat_id, user_id)
                    if chat_member.status in ['creator', 'administrator']:
                        # Сохраняем в кэш
                        self._admins_cache[cache_key] = True
                        self._cache_expiry[cache_key] = current_time
                        return True
                except Exception as group_admin_error:
                    logger.debug(f"Пользователь {user_id} не админ группы {chat_id}: {group_admin_error}")

            # Проверяем права администратора бота через базу данных
            from database.crud import UserRepository
            from database import SessionLocal

            db = SessionLocal()
            try:
                user = UserRepository.get_user_by_telegram_id(db, user_id)
                is_admin = bool(user and user.is_admin)

                # Сохраняем в кэш
                self._admins_cache[cache_key] = is_admin
                self._cache_expiry[cache_key] = current_time

                return is_admin
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Ошибка при проверке прав администратора: {e}")

        return False

    def clear_cache(self, user_id: Optional[int] = None, chat_id: Optional[int] = None):
        """Очищает кэш админов"""
        if user_id and chat_id:
            cache_key = f"{user_id}_{chat_id}"
            self._admins_cache.pop(cache_key, None)
            self._cache_expiry.pop(cache_key, None)
        else:
            self._admins_cache.clear()
            self._cache_expiry.clear()


# Создаем глобальный экземпляр
state_manager = RouletteStateManager()