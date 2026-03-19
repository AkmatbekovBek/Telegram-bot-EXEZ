# handlers/history/race_history.py
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from .base_handler import BaseHistoryHandler


class RaceHistoryHandler(BaseHistoryHandler):
    """Обработчик истории гонок"""

    def __init__(self):
        super().__init__()
        self.handler_type = "race"

    def get_history(self, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """Получает историю гонок пользователя"""
        try:
            # Ищем транзакции связанные с гонками
            query = text("""
                         SELECT t.timestamp,
                                t.amount,
                                t.description,
                                CASE
                                    WHEN t.from_user_id = :user_id THEN 'outgoing'
                                    WHEN t.to_user_id = :user_id THEN 'incoming'
                                    ELSE 'unknown'
                                    END                                          as direction,
                                COALESCE(tu1.username, tu1.first_name, 'Аноним') as from_user_name,
                                COALESCE(tu2.username, tu2.first_name, 'Аноним') as to_user_name
                         FROM transactions t
                                  LEFT JOIN telegram_users tu1 ON t.from_user_id = tu1.telegram_id
                                  LEFT JOIN telegram_users tu2 ON t.to_user_id = tu2.telegram_id
                         WHERE (t.from_user_id = :user_id OR t.to_user_id = :user_id)
                           AND (
                             t.description LIKE '%гонк%' OR
                             t.description LIKE '%race%' OR
                             t.description LIKE '%🏎️%' OR
                             t.description LIKE '%🏁%' OR
                             t.description LIKE '%победитель гонки%' OR
                             t.description LIKE '%проигрыш в гонке%'
                             )
                         ORDER BY t.timestamp DESC LIMIT 20
                         """)

            result = db.execute(query, {'user_id': user_id})
            history_entries = []

            for row in result:
                if not self._is_today(row.timestamp):
                    continue

                time_str = self._format_time(row.timestamp)
                description = row.description or ""

                # Определяем тип операции
                if "победитель гонки" in description.lower() and row.direction == "incoming":
                    entry_text = f"{time_str} 🏎️ Победитель гонки: +{row.amount:,}"
                elif "проигрыш в гонке" in description.lower() and row.direction == "outgoing":
                    entry_text = f"{time_str} 🏎️ Проигрыш в гонке: -{row.amount:,}"
                elif "ставка в гонке" in description.lower() and row.direction == "outgoing":
                    entry_text = f"{time_str} 🏎️ Ставка в гонке: -{row.amount:,}"
                elif "возврат ставки" in description.lower() and row.direction == "incoming":
                    entry_text = f"{time_str} 🏎️ Возврат ставки: +{row.amount:,}"
                elif "гонка" in description.lower():
                    if row.direction == "incoming":
                        entry_text = f"{time_str} 🏎️ Выигрыш в гонке: +{row.amount:,}"
                    else:
                        entry_text = f"{time_str} 🏎️ Ставка в гонке: -{row.amount:,}"
                else:
                    # Общий случай для гонок
                    if row.direction == "incoming":
                        entry_text = f"{time_str} 🏎️ Получено от гонки: +{row.amount:,}"
                    else:
                        entry_text = f"{time_str} 🏎️ Потрачено на гонку: -{row.amount:,}"

                history_entries.append({
                    'timestamp': row.timestamp,
                    'text': entry_text
                })

            return history_entries

        except Exception as e:
            print(f"❌ Ошибка получения истории гонок: {e}")
            return []