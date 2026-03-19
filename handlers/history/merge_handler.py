# handlers/history/merge_handler.py
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from .base_handler import BaseHistoryHandler
from .roulette_history import RouletteHistoryHandler
from .race_history import RaceHistoryHandler
from .dice_history import DiceHistoryHandler
from .slot_history import SlotHistoryHandler
from .gift_history import GiftHistoryHandler
from .transfer_history import TransferHistoryHandler
from .rps_history import RPSHistoryHandler
from .raffle_history import RaffleHistoryHandler


class HistoryMergeHandler:
    """Объединяет историю из всех источников"""

    def __init__(self):
        self.handlers = {
            'roulette': RouletteHistoryHandler(),
            'race': RaceHistoryHandler(),
            'dice': DiceHistoryHandler(),
            'slot': SlotHistoryHandler(),
            'rps': RPSHistoryHandler(),
            'gift': GiftHistoryHandler(),
            'transfer': TransferHistoryHandler(),
            'raffle': RaffleHistoryHandler(),

        }

    def get_complete_history(self, db: Session, user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
        """Получает полную историю из всех источников"""
        all_history_entries = []

        # Собираем историю из всех обработчиков
        for handler_name, handler in self.handlers.items():
            try:
                entries = handler.get_history(db, user_id)
                all_history_entries.extend(entries)
            except Exception as e:
                print(f"❌ Ошибка в обработчике {handler_name}: {e}")
                continue

        # Сортируем все записи по времени (от старых к новым)
        all_history_entries.sort(key=lambda x: x['timestamp'])

        # Берем последние N записей (самые новые)
        recent_history = all_history_entries[-limit:] if len(all_history_entries) > limit else all_history_entries

        return recent_history

    def get_formatted_history(self, db: Session, user_id: int, limit: int = 12) -> str:
        """Возвращает отформатированную историю"""
        history_entries = self.get_complete_history(db, user_id, limit)

        if not history_entries:
            return "📊 *История операций за сегодня:*\nПока нет записей"

        # Формируем строку истории
        history_lines = [entry['text'] for entry in history_entries]
        history_text = "📊 *История операций*\n" + "\n".join(history_lines)

        return history_text