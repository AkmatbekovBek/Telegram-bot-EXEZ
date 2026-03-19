import random
import asyncio
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Tuple, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .config import CONFIG


import secrets

class RouletteGame:
    def __init__(self):
        self.numbers = list(CONFIG.NUMBERS)
        # self._rng = random.Random() # Not needed with secrets
        self.standard_groups = {
            "1-3": {1, 2, 3}, "4-6": {4, 5, 6},
            "7-9": {7, 8, 9}, "10-12": {10, 11, 12}
        }
        self.last_results = []
        self.max_same_color_streak = 4  # Увеличил до 4 одинаковых цветов подряд
        self.chat_stats = {}

    def _get_chat_stats(self, chat_id):
        if chat_id not in self.chat_stats:
            self.chat_stats[chat_id] = {
                'last_results': [],
                'color_streak': 0,
                'last_color': None,
                'last_number': None,
                'recent_numbers': [],
                'recent_colors': []  # Отдельно храним последние цвета
            }
        return self.chat_stats[chat_id]

    def _get_available_numbers(self, exclude_color: str = None, exclude_number: int = None):
        """Получает доступные числа для выбора"""
        available_numbers = self.numbers.copy()

        if exclude_color == "красное":
            available_numbers = [n for n in available_numbers if n not in CONFIG.RED_NUMBERS]
        elif exclude_color == "черное":
            available_numbers = [n for n in available_numbers if n not in CONFIG.BLACK_NUMBERS]
        elif exclude_color == "зеленое":
            available_numbers = [n for n in available_numbers if n != 0]

        if exclude_number is not None and exclude_number in available_numbers:
            available_numbers.remove(exclude_number)

        return available_numbers

    def spin(self, chat_id: int = 0) -> int:
        """Генерирует число с криптографически стойким рандомом"""
        # Используем secrets для истинного рандома
        # random.choice не совсем подходит для казино-логики, лучше secrets.randbelow
        
        # Получаем случайный индекс от 0 до 12 (всего 13 чисел: 0-12)
        random_index = secrets.randbelow(13)
        result = self.numbers[random_index]

        # Обновляем статистику (только для логов, не влияет на результат)
        self._update_stats(result, chat_id)

        return result

    def _generate_natural_random(self, stats):
        """Генерирует число с естественным рандомом"""
        # 10% шанс на зеленое
        if random.random() < 0.10:
            return 0

        # Если уже 3 одинаковых цвета подряд, увеличиваем шанс на смену
        if stats['color_streak'] >= 3 and stats['last_color'] in ['красное', 'черное']:
            # 80% шанс на противоположный цвет
            if random.random() < 0.8:
                if stats['last_color'] == 'красное':
                    return random.choice(list(CONFIG.BLACK_NUMBERS))
                else:
                    return random.choice(list(CONFIG.RED_NUMBERS))

        # Чистый рандом с небольшим смещением против паттернов
        rand_val = random.random()

        # Смещаем распределение чтобы избежать 50/50
        if rand_val < 0.48:  # 48% на красное
            return random.choice(list(CONFIG.RED_NUMBERS))
        else:  # 52% на черное (немного больше)
            return random.choice(list(CONFIG.BLACK_NUMBERS))

    def _update_stats(self, result: int, chat_id: int):
        """Обновляет статистику после спина"""
        stats = self._get_chat_stats(chat_id)
        result_color = self.get_color(result)

        # Обновляем статистику серии
        if result_color == stats['last_color']:
            stats['color_streak'] += 1
        else:
            stats['color_streak'] = 1
            stats['last_color'] = result_color

        stats['last_number'] = result

        # Сохраняем последние числа и цвета
        stats['recent_numbers'].append(result)
        if len(stats['recent_numbers']) > 6:  # Храним больше истории
            stats['recent_numbers'] = stats['recent_numbers'][-6:]

        stats['recent_colors'].append(result_color)
        if len(stats['recent_colors']) > 6:
            stats['recent_colors'] = stats['recent_colors'][-6:]

        # Обновляем историю результатов
        stats['last_results'].append(result)
        if len(stats['last_results']) > 20:
            stats['last_results'] = stats['last_results'][-20:]

        # Сохраняем общую историю для всех чатов
        self.last_results.append(result)
        if len(self.last_results) > 50:
            self.last_results = self.last_results[-50:]

    def get_color(self, number: int) -> str:
        if number == 0:
            return "зеленое"
        return "красное" if number in CONFIG.RED_NUMBERS else "черное"

    def get_color_emoji(self, number: int) -> str:
        if number == 0:
            return "💚"
        return "🔴" if number in CONFIG.RED_NUMBERS else "⚫"

    def check_bet(self, bet_type: str, bet_value: Any, result: int) -> bool:
        try:
            if bet_type == "число":
                num_value = int(bet_value) if isinstance(bet_value, str) else bet_value
                return num_value == result
            elif bet_type == "цвет":
                # Важно: правильная проверка для зеленого
                if bet_value == "зеленое":
                    return result == 0  # Только если выпало 0
                elif bet_value == "красное":
                    return result in CONFIG.RED_NUMBERS
                elif bet_value == "черное":
                    return result in CONFIG.BLACK_NUMBERS
                return False
            elif bet_type == "группа":
                if bet_value in self.standard_groups:
                    return result in self.standard_groups[bet_value]
                if isinstance(bet_value, str) and '-' in bet_value:
                    try:
                        start, end = map(int, bet_value.split('-'))
                        if 0 <= start <= 12 and 0 <= end <= 12 and start <= end:
                            return start <= result <= end
                    except (ValueError, TypeError):
                        return False
            return False
        except (ValueError, TypeError):
            return False

    def get_multiplier(self, bet_type: str, bet_value: Any) -> Decimal:
        if bet_type == "число":
            return CONFIG.PAYOUTS["число"]
        elif bet_type == "цвет":
            color_key = f"цвет_{bet_value}"
            return CONFIG.PAYOUTS.get(color_key, Decimal('1.0'))
        elif bet_type == "группа":
            if isinstance(bet_value, str) and '-' in bet_value:
                try:
                    start, end = map(int, bet_value.split('-'))
                    if 0 <= start <= 12 and 0 <= end <= 12 and start <= end:
                        count = end - start + 1
                        return (CONFIG.PAYOUTS["число"] / Decimal(count)).quantize(
                            Decimal('0.001'), rounding=ROUND_DOWN
                        )
                except (ValueError, TypeError):
                    pass
            return CONFIG.PAYOUTS["группа_стандарт"]
        return Decimal('1.0')

    def get_color_streak_info(self, chat_id: int = 0) -> str:
        """Возвращает информацию о текущей серии цветов"""
        stats = self._get_chat_stats(chat_id)
        if not stats['last_color']:
            return "История цветов пуста"

        return f"Текущая серия: {stats['last_color']} ({stats['color_streak']} раз подряд)"

    def get_recent_history(self, chat_id: int = 0, limit: int = 10) -> list:
        """Возвращает последние результаты"""
        stats = self._get_chat_stats(chat_id)
        return stats['last_results'][-limit:] if stats['last_results'] else []


class RouletteKeyboard:
    @staticmethod
    def create_roulette_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(row_width=4).row(
            InlineKeyboardButton("1-3", callback_data="bet:1-3"),
            InlineKeyboardButton("4-6", callback_data="bet:4-6"),
            InlineKeyboardButton("7-9", callback_data="bet:7-9"),
            InlineKeyboardButton("10-12", callback_data="bet:10-12"),
        ).row(
            InlineKeyboardButton("1к 🔴", callback_data="quick:1000_red"),
            InlineKeyboardButton("1к ⚫", callback_data="quick:1000_black"),
            InlineKeyboardButton("1к 💚", callback_data="quick:1000_green"),
        ).row(
            InlineKeyboardButton("Повторить", callback_data="action:repeat"),
            InlineKeyboardButton("Удвоить", callback_data="action:double"),
            InlineKeyboardButton("Крутить", callback_data="action:spin"),
        )


class AntiFloodManager:
    __slots__ = ('user_last_spin', 'user_spin_count', 'user_spin_reset_time')

    def __init__(self):
        self.user_last_spin: Dict[Tuple[int, int], float] = {}
        self.user_spin_count: Dict[Tuple[int, int], int] = {}
        self.user_spin_reset_time: Dict[Tuple[int, int], float] = {}

    def can_spin(self, user_id: int, chat_id: int) -> Tuple[bool, float]:
        key = (user_id, chat_id)
        current_time = asyncio.get_event_loop().time()
        if key in self.user_last_spin:
            last_spin_time = self.user_last_spin[key]
            elapsed = current_time - last_spin_time
            if elapsed < CONFIG.MIN_SPIN_INTERVAL:
                return False, CONFIG.MIN_SPIN_INTERVAL - elapsed
        if key not in self.user_spin_count:
            self.user_spin_count[key] = 0
            self.user_spin_reset_time[key] = current_time
        if current_time - self.user_spin_reset_time[key] > CONFIG.RESET_INTERVAL:
            self.user_spin_count[key] = 0
            self.user_spin_reset_time[key] = current_time
        if self.user_spin_count[key] >= CONFIG.MAX_SPINS_PER_MINUTE:
            time_until_reset = CONFIG.RESET_INTERVAL - (current_time - self.user_spin_reset_time[key])
            return False, time_until_reset
        self.user_last_spin[key] = current_time
        self.user_spin_count[key] += 1
        return True, 0

    def cleanup_old_entries(self):
        current_time = asyncio.get_event_loop().time()
        old_keys = [
            key for key, timestamp in self.user_last_spin.items()
            if current_time - timestamp > CONFIG.CLEANUP_INTERVAL
        ]
        for key in old_keys:
            self.user_last_spin.pop(key, None)
            self.user_spin_count.pop(key, None)
            self.user_spin_reset_time.pop(key, None)