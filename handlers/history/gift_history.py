# handlers/history/gift_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class GiftHistoryHandler(BaseHistoryHandler):
    """Обработчик истории подарков"""

    def __init__(self):
        super().__init__()
        self.handler_type = "gift"

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
        """Получает историю подарков пользователя"""
        try:
            from database.models import Transaction, Gift, UserGift

            history_entries = []

            # 1. Обрабатываем транзакции подарков
            transactions = db.query(Transaction).filter(
                (Transaction.from_user_id == user_id) |
                (Transaction.to_user_id == user_id)
            ).order_by(Transaction.timestamp.desc()).limit(30).all()

            for transaction in transactions:
                if not self._is_today(transaction.timestamp):
                    continue

                time_str = self._format_time(transaction.timestamp)
                description = transaction.description or ""

                # Проверяем, является ли транзакция подарком
                if any(marker in description.lower() for marker in [
                    'подарок', 'gift', '🎁', 'подарил', 'получил в подарок'
                ]):
                    if transaction.to_user_id == user_id and "получил в подарок" in description.lower():
                        # Получение подарка
                        gift_desc = description.replace("получил в подарок ", "").replace(" от игрока", "")
                        source_name = self._get_user_display_name(db, transaction.from_user_id)
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🎁 Получен подарок: {gift_desc} от {source_name}"
                        })
                    elif transaction.from_user_id == user_id and "подарил" in description.lower():
                        # Отправка подарка
                        gift_desc = description.replace("подарил ", "").replace(" игроку", "")
                        target_name = self._get_user_display_name(db, transaction.to_user_id)
                        history_entries.append({
                            'timestamp': transaction.timestamp,
                            'text': f"{time_str} 🎁 Подарок отправлен: {gift_desc} для {target_name}"
                        })

            # 2. Обрабатываем покупки подарков из таблицы user_gifts
            user_gifts = db.query(UserGift).filter(
                UserGift.user_id == user_id
            ).order_by(UserGift.created_at.desc()).limit(20).all()

            for user_gift in user_gifts:
                if not self._is_today(user_gift.created_at):
                    continue

                time_str = self._format_time(user_gift.created_at)
                gift = db.query(Gift).filter(Gift.id == user_gift.gift_id).first()

                if gift:
                    if user_gift.quantity > 0:
                        history_entries.append({
                            'timestamp': user_gift.created_at,
                            'text': f"{time_str} 🎁 Куплен подарок: {gift.name} x{user_gift.quantity}"
                        })

            return history_entries

        except Exception as e:
            print(f"❌ Ошибка получения истории подарков: {e}")
            return []