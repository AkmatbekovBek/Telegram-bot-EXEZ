from datetime import datetime, date
from collections import deque
import logging
from database import get_db
from database.crud import RouletteRepository


class RouletteLogger:
    """Класс для логирования результатов рулетки с сохранением в БД"""

    def __init__(self):
        self.chat_logs = {}  # {chat_id: deque} - кэш логов по чатам
        self.current_date = date.today()
        self.logger = logging.getLogger(__name__)

    def add_game_log(self, chat_id: int, result: int, color_emoji: str):
        """Добавляет запись о результате игры в БД и кэш"""
        try:
            db = next(get_db())

            # Сохраняем в базу данных (постоянное хранение)
            RouletteRepository.add_game_log(db, chat_id, result, color_emoji)

            # Также обновляем кэш в памяти для быстрого доступа
            if chat_id not in self.chat_logs:
                self.chat_logs[chat_id] = deque(maxlen=50)  # Храним до 50 записей в кэше

            game_log = {
                "result": result,
                "color_emoji": color_emoji,
                "timestamp": datetime.now()
            }
            
            # ВСЕГДА добавляем новые логи В КОНЕЦ (вниз)
            self.chat_logs[chat_id].append(game_log)

            self.logger.info(f"Добавлен лог рулетки для чата {chat_id}: {result}{color_emoji}")

        except Exception as e:
            self.logger.error(f"Ошибка добавления лога рулетки: {e}")

    def get_recent_logs(self, chat_id: int, count: int = 10):
        """Возвращает последние N записей для чата (последние снизу)"""
        try:
            # Сначала пробуем получить из кэша
            if chat_id in self.chat_logs and self.chat_logs[chat_id]:
                logs = list(self.chat_logs[chat_id])
                # Берем последние N записей и НЕ реверсируем - они уже в правильном порядке
                # (старые в начале, новые в конце)
                return logs[-count:] if len(logs) >= count else logs

            # Если в кэше недостаточно данных, берем из БД
            db = next(get_db())
            logs = RouletteRepository.get_recent_game_logs(db, chat_id, count)

            # Преобразуем в нужный формат и НЕ реверсируем
            formatted_logs = []
            for log in logs:
                formatted_logs.append({
                    "result": log.result,
                    "color_emoji": log.color_emoji,
                    "timestamp": log.created_at
                })

            return formatted_logs  # НЕ реверсируем - порядок уже правильный

        except Exception as e:
            self.logger.error(f"Ошибка получения логов: {e}")
            return []

    def get_all_logs(self, chat_id: int):
        """Возвращает все логи для чата (до 50, последние снизу)"""
        try:
            # Сначала пробуем получить из кэша
            if chat_id in self.chat_logs and self.chat_logs[chat_id]:
                logs = list(self.chat_logs[chat_id])
                # Возвращаем все логи в исходном порядке (старые -> новые)
                return logs

            # Если в кэше недостаточно данных, берем из БД
            db = next(get_db())
            logs = RouletteRepository.get_recent_game_logs(db, chat_id, 50)

            # Преобразуем в нужный формат и НЕ реверсируем
            formatted_logs = []
            for log in logs:
                formatted_logs.append({
                    "result": log.result,
                    "color_emoji": log.color_emoji,
                    "timestamp": log.created_at
                })

            return formatted_logs  # НЕ реверсируем - порядок уже правильный

        except Exception as e:
            self.logger.error(f"Ошибка получения всех логов: {e}")
            return []

    def get_logs_count(self, chat_id: int):
        """Возвращает количество записей в логах чата из БД"""
        try:
            db = next(get_db())

            # Получаем количество логов через SQLAlchemy
            from sqlalchemy import func
            from database.models import RouletteGameLog

            count = db.query(func.count(RouletteGameLog.id)).filter(
                RouletteGameLog.chat_id == chat_id
            ).scalar()

            return count if count else 0

        except Exception as e:
            self.logger.error(f"Ошибка подсчета логов: {e}")
            return 0

    def cleanup_old_logs(self, days: int = 30):
        """Очищает старые логи (старше указанного количества дней)"""
        try:
            db = next(get_db())
            from sqlalchemy import delete
            from database.models import RouletteGameLog
            from datetime import datetime, timedelta

            cutoff_date = datetime.now() - timedelta(days=days)

            deleted_count = db.execute(
                delete(RouletteGameLog).where(
                    RouletteGameLog.created_at < cutoff_date
                )
            ).rowcount

            db.commit()

            # Также очищаем кэш для всех чатов
            self.chat_logs.clear()

            self.logger.info(f"Очищено {deleted_count} старых логов рулетки")
            return deleted_count

        except Exception as e:
            self.logger.error(f"Ошибка очистки старых логов: {e}")
            return 0
