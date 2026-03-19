# handlers/history/slot_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class SlotHistoryHandler(BaseHistoryHandler):
    """Обработчик истории игровых автоматов"""

    def __init__(self):
        super().__init__()
        self.handler_type = "slot"

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю игровых автоматов пользователя"""
        try:
            from database.models import Transaction

            # Получаем все транзакции пользователя
            transactions = db.query(Transaction).filter(
                (Transaction.from_user_id == user_id) |
                (Transaction.to_user_id == user_id)
            ).order_by(Transaction.timestamp.desc()).limit(30).all()

            history_entries = []

            for transaction in transactions:
                if not self._is_today(transaction.timestamp):
                    continue

                time_str = self._format_time(transaction.timestamp)
                description = transaction.description or ""

                # Ищем транзакции слота по ключевым словам
                if any(keyword in description for keyword in [
                    '🎰', 'слот', 'slot', 'автомат', 'комбинация', 'СЛОТ', 'АВТОМАТ'
                ]):
                    # Определяем направление транзакции
                    if transaction.from_user_id == user_id:
                        # Исходящая транзакция (ставка/проигрыш)
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🎰 Ставка в слотах: -{transaction.amount:,}"
                        })
                    elif transaction.to_user_id == user_id:
                        # Входящая транзакция (выигрыш)
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🎰 Выигрыш в слотах: +{transaction.amount:,}"
                        })

            return history_entries

        except Exception as e:
            print(f"❌ Ошибка получения истории слотов: {e}")
            return []