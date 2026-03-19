# handlers/history/base_handler.py
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session


class BaseHistoryHandler:
    """Базовый класс для всех обработчиков истории"""

    def __init__(self):
        self.handler_type = "base"

    def _format_time(self, timestamp) -> str:
        """Format timestamp to [HH:MM:SS] format"""
        try:
            if not timestamp:
                return '[--:--:--]'

            if isinstance(timestamp, datetime):
                return timestamp.strftime('[%H:%M:%S]')

            if isinstance(timestamp, str):
                timestamp = timestamp.replace('T', ' ').replace('Z', '')
                formats = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M:%S.%f',
                    '%H:%M:%S',
                    '%H:%M:%S.%f'
                ]
                for fmt in formats:
                    try:
                        dt = datetime.strptime(timestamp, fmt)
                        return dt.strftime('[%H:%M:%S]')
                    except ValueError:
                        continue
            return '[--:--:--]'
        except Exception:
            return '[--:--:--]'

    def _is_today(self, timestamp) -> bool:
        """Check if timestamp is from today"""
        try:
            if isinstance(timestamp, datetime):
                return timestamp.date() == date.today()
            elif isinstance(timestamp, str):
                timestamp = timestamp.replace('T', ' ').replace('Z', '')
                formats = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M:%S.%f'
                ]
                for fmt in formats:
                    try:
                        dt = datetime.strptime(timestamp, fmt)
                        return dt.date() == date.today()
                    except ValueError:
                        continue
            return False
        except:
            return False

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю для конкретного пользователя"""
        raise NotImplementedError("Метод должен быть реализован в дочернем классе")