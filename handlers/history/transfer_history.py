# handlers/history/transfer_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class TransferHistoryHandler(BaseHistoryHandler):
    """Обработчик истории переводов"""

    def __init__(self):
        super().__init__()
        self.handler_type = "transfer"

    def _get_user_display_name(self, db: Session, user_id: int) -> str:
        """Получает отображаемое имя пользователя"""
        try:
            from database.models import TelegramUser
            user = db.query(TelegramUser).filter(
                TelegramUser.telegram_id == user_id
            ).first()

            if not user:
                return "Аноним"

            if user.first_name:
                return user.first_name[:15]
            elif user.username:
                return f"@{user.username}"
            else:
                return "Аноним"
        except:
            return "Аноним"

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю переводов пользователя"""
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

                # Пропускаем донаты, подарки и результаты игр (они обрабатываются отдельно)
                if any(marker in description.lower() for marker in [
                    'донат', 'donate', '💎', 'админ пополнение',
                    'подарок', 'gift', '🎁',
                    'рулетк', 'roulette', 'гонк', 'race',
                    'кубик', 'dice', 'слот', 'slot', 'кнб'
                ]):
                    continue

                # Определяем тип операции
                if transaction.from_user_id == user_id:
                    # Исходящий перевод
                    if transaction.to_user_id:
                        target_name = self._get_user_display_name(db, transaction.to_user_id)
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 💸 Перевод: -{transaction.amount:,} для {target_name}"
                        })
                else:
                    # Входящий перевод
                    if transaction.from_user_id:
                        source_name = self._get_user_display_name(db, transaction.from_user_id)
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 💰 Получено: +{transaction.amount:,} от {source_name}"
                        })

            return history_entries

        except Exception as e:
            print(f"❌ Ошибка получения истории переводов: {e}")
            return []