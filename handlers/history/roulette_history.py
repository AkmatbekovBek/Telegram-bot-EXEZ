# handlers/history/roulette_history.py
from datetime import datetime, date
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler


class RouletteHistoryHandler(BaseHistoryHandler):
    """Обработчик истории рулетки с группировкой"""

    def __init__(self):
        super().__init__()
        self.handler_type = "roulette"

    def _format_datetime(self, timestamp) -> str:
        """Format timestamp to [DD.MM HH:MM:SS] or [HH:MM:SS] for today"""
        try:
            if not timestamp:
                return '[--:--:--]'

            if isinstance(timestamp, datetime):
                dt = timestamp
            else:
                # Пробуем распарсить строку
                timestamp_str = str(timestamp)
                formats = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M:%S.%f',
                    '%H:%M:%S',
                    '%H:%M:%S.%f'
                ]
                for fmt in formats:
                    try:
                        dt = datetime.strptime(timestamp_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return '[--:--:--]'

            # Проверяем, сегодня ли это
            if dt.date() == date.today():
                # Для сегодняшнего дня: [HH:MM:SS]
                return dt.strftime('[%H:%M:%S]')
            else:
                # Для старых дней: [DD.MM HH:MM]
                return dt.strftime('[%d.%m %H:%M]')
        except Exception:
            return '[--:--:--]'

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю ставок в рулетке - показывает общий результат для ставок с одинаковым временем"""
        try:
            from database.models import RouletteTransaction

            # Получаем историю ставок
            bet_history = db.query(RouletteTransaction).filter(
                RouletteTransaction.user_id == user_id
            ).order_by(RouletteTransaction.created_at.desc()).limit(50).all()

            if not bet_history:
                return []

            # Группируем транзакции по точному времени (до секунд)
            grouped_transactions = {}

            for transaction in bet_history:
                # Используем время как ключ для группировки (обрезаем до секунд)
                time_key = transaction.created_at.replace(microsecond=0)

                if time_key not in grouped_transactions:
                    grouped_transactions[time_key] = {
                        'transactions': [],
                        'total_amount': 0,
                        'total_profit': 0
                    }

                grouped_transactions[time_key]['transactions'].append(transaction)
                grouped_transactions[time_key]['total_amount'] += int(transaction.amount)

                # Рассчитываем прибыль для этой транзакции
                if hasattr(transaction, 'profit') and transaction.profit is not None:
                    profit = int(transaction.profit)
                elif transaction.is_win:
                    profit = int(transaction.amount)
                else:
                    profit = -int(transaction.amount)

                grouped_transactions[time_key]['total_profit'] += profit

            history_entries = []

            # Сортируем группы по времени (от новых к старым)
            sorted_times = sorted(grouped_transactions.keys(), reverse=True)

            for time_key in sorted_times:
                group = grouped_transactions[time_key]
                time_str = self._format_datetime(time_key)
                total_profit = group['total_profit']

                if total_profit > 0:
                    history_entries.append({
                        'timestamp': time_key,
                        'text': f"{time_str} 🎰 Выигрыш рулетки: +{total_profit:,}"
                    })
                elif total_profit < 0:
                    history_entries.append({
                        'timestamp': time_key,
                        'text': f"{time_str} 🎰 Проигрыш рулетки: {total_profit:,}"
                    })
                else:
                    history_entries.append({
                        'timestamp': time_key,
                        'text': f"{time_str} 🎰 Ничья в рулетке: 0"
                    })

            return history_entries

        except Exception as e:
            print(f"Ошибка получения истории рулетки: {e}")
            return []