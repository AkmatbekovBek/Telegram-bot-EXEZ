# handlers/history/dice_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class DiceHistoryHandler(BaseHistoryHandler):
    """Обработчик истории игры в кубики"""

    def __init__(self):
        super().__init__()
        self.handler_type = "dice"

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю игры в кубики"""
        try:
            from database.models import Transaction

            # Ищем транзакции связанные с игрой в кубики
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

                # Проверяем, является ли транзакция связанной с кубиками
                if any(marker in description.lower() for marker in [
                    'кубик', 'dice', '🎲', 'игра в кубики',
                    'выигрыш кубик', 'проигрыш кубик'
                ]):
                    if transaction.to_user_id == user_id and any(
                            word in description.lower() for word in ['выигрыш', 'win']):
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🎲 Выигрыш в кубики: +{transaction.amount:,}"
                        })
                    elif transaction.from_user_id == user_id and any(
                            word in description.lower() for word in ['проигрыш', 'lose']):
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🎲 Проигрыш в кубики: -{transaction.amount:,}"
                        })
                    elif "кубик" in description.lower():
                        if transaction.to_user_id == user_id:
                            history_entries.append({
                                'timestamp': transaction.timestamp,
                                'text': f"{time_str} 🎲 Получено от кубиков: +{transaction.amount:,}"
                            })
                        else:
                            history_entries.append({
                                'timestamp': transaction.timestamp,
                                'text': f"{time_str} 🎲 Потрачено на кубики: -{transaction.amount:,}"
                            })

            return history_entries

        except Exception as e:
            print(f"❌ Ошибка получения истории кубиков: {e}")
            return []