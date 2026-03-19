# handlers/history/raffle_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class RaffleHistoryHandler(BaseHistoryHandler):
    """Обработчик истории розыгрышей"""

    def __init__(self):
        super().__init__()
        self.handler_type = "raffle"

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю розыгрышей пользователя"""
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

                # Ищем транзакции розыгрышей по ключевым словам
                if any(keyword in description.lower() for keyword in [
                    'розыгрыш', 'раффл', 'выигрыш в розыгрыше', '🏆', '🎉'
                ]):
                    # Определяем направление транзакции
                    if transaction.from_user_id == user_id:
                        # Пользователь создал розыгрыш (это должно быть отдельной транзакцией)
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🎉 Создан розыгрыш: -{transaction.amount:,}"
                        })
                    elif transaction.to_user_id == user_id:
                        # Пользователь выиграл в розыгрыше
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🏆 Выигрыш в розыгрыше: +{transaction.amount:,}"
                        })

            return history_entries

        except Exception as e:
            print(f"❌ Ошибка получения истории розыгрышей: {e}")
            return []

class RaffleHistoryHandler(BaseHistoryHandler):
    """Обработчик истории розыгрышей"""

    def __init__(self):
        super().__init__()
        self.handler_type = "raffle"

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю розыгрышей пользователя"""
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

                # Исключаем транзакции гонок
                if any(keyword in description.lower() for keyword in [
                    'гонк', 'race', '🏎️', '🏁', 'победитель гонки', 'проигрыш в гонке'
                ]):
                    continue  # Пропускаем транзакции гонок

                # Ищем транзакции розыгрышей по ключевым словам
                if any(keyword in description.lower() for keyword in [
                    'розыгрыш', 'раффл', 'выигрыш в розыгрыше', '🎉'
                ]):
                    # Определяем направление транзакции
                    if transaction.from_user_id == user_id:
                        # Пользователь создал розыгрыш
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🎉 Создан розыгрыш: -{transaction.amount:,}"
                        })
                    elif transaction.to_user_id == user_id:
                        # Пользователь выиграл в розыгрыше
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🎉 Выигрыш в розыгрыше: +{transaction.amount:,}"
                        })

            return history_entries

        except Exception as e:
            print(f"❌ Ошибка получения истории розыгрышей: {e}")
            return []