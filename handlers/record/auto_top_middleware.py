import logging
import time
from typing import Dict, Tuple

from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware

from .services import RecordService
from .record_core import RecordCore

logger = logging.getLogger(__name__)


class AutoTopMiddleware(BaseMiddleware):
    """
    Middleware для автоматической регистрации пользователей в топе чата (UserChat),
    чтобы они появлялись в "топ богатеев" без необходимости писать "топ".

    ВАЖНО:
    - Работает только в group/supergroup
    - Пропускает команды с '/'
    - Есть антиспам (throttle), чтобы не дергать БД на каждое сообщение бесконечно
    """

    def __init__(self, throttle_seconds: int = 3600):
        super().__init__()
        self.core = RecordCore()
        self.service = RecordService(self.core)
        self.throttle_seconds = max(5, int(throttle_seconds))

        # (chat_id, user_id) -> last_ts
        self._last_seen: Dict[Tuple[int, int], float] = {}

    def _should_skip(self, message: types.Message) -> bool:
        if not message or not message.from_user or not message.chat:
            return True

        # Только группы
        if message.chat.type not in ("group", "supergroup"):
            return True

        # Пропускаем slash-команды
        if message.text and message.text.strip().startswith("/"):
            return True

        return False

    def _throttled(self, chat_id: int, user_id: int) -> bool:
        now = time.monotonic()
        key = (chat_id, user_id)
        last = self._last_seen.get(key)

        if last is not None and (now - last) < self.throttle_seconds:
            return True

        self._last_seen[key] = now

        # лёгкая зачистка, чтобы dict не рос бесконечно
        if len(self._last_seen) > 200_000:
            cutoff = now - (self.throttle_seconds * 2)
            self._last_seen = {k: v for k, v in self._last_seen.items() if v >= cutoff}

        return False

    async def on_pre_process_message(self, message: types.Message, data: dict):
        try:
            if self._should_skip(message):
                return

            user_id = message.from_user.id
            chat_id = message.chat.id

            if self._throttled(chat_id, user_id):
                return

            await self.service.register_user_for_chat_top(
                user_id=user_id,
                chat_id=chat_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name
            )

        except Exception as e:
            logger.error(f"Error in AutoTopMiddleware: {e}")
