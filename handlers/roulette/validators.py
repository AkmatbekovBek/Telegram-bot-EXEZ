#handlers/roulette/validators.py
import re
from decimal import Decimal, ROUND_DOWN
from typing import Tuple, List, Optional, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager
from aiogram import types

from .config import CONFIG
from database import get_db
from database.crud import UserRepository


class UserFormatter:
    ESCAPE_CHARS = r'_*[]()~`>#+-=|{}.!'

    @staticmethod
    def escape_markdown(text: str) -> str:
        return ''.join(f'\\{char}' if char in UserFormatter.ESCAPE_CHARS else char for char in text)

    @staticmethod
    def get_user_link(user_id: int, display_name: str) -> str:
        safe_name = UserFormatter.escape_markdown(display_name)
        return f"[{safe_name}](tg://user?id={user_id})"

    @staticmethod
    def format_username(user: types.User) -> str:
        display_name = UserFormatter._get_display_name(user)
        return UserFormatter.get_user_link(user.id, display_name)

    @staticmethod
    def get_plain_name(display_name: str) -> str:
        return UserFormatter.escape_markdown(display_name)

    @staticmethod
    def _get_display_name(user: types.User) -> str:
        if user.first_name:
            return user.first_name
        elif user.username:
            return f"@{user.username}"
        else:
            return f"Пользователь {user.id}"


class DatabaseManager:
    @staticmethod
    @asynccontextmanager
    async def db_session():
        db = next(get_db())
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    async def update_users_batch(user_updates: Dict[int, int], user_stats_updates: Dict[int, Tuple]):
        import logging
        logger = logging.getLogger(__name__)
        async with DatabaseManager.db_session() as db:
            try:
                for user_id, new_coins in user_updates.items():
                    user = UserRepository.get_user_by_telegram_id(db, user_id)
                    if user:
                        user.coins = new_coins
                for user_id, stats in user_stats_updates.items():
                    user = UserRepository.get_user_by_telegram_id(db, user_id)
                    if user:
                        win_coins, defeat_coins, max_win, min_win, max_bet = stats  # ← 5 элементов
                        if win_coins is not None:
                            user.win_coins = win_coins
                        if defeat_coins is not None:
                            user.defeat_coins = defeat_coins
                        if max_win is not None:
                            user.max_win_coins = max_win
                        if min_win is not None:
                            user.min_win_coins = min_win
                        if max_bet is not None:  # ← добавлено
                            user.max_bet_coins = max_bet
                db.commit()
                logger.info(f"✅ Пакетное обновление: {len(user_updates)} пользователей")
            except Exception as e:
                db.rollback()
                logger.error(f"❌ Ошибка пакетного обновления БД: {e}")
                raise


class BetValidator:
    @staticmethod
    def validate_bet(amount: int, user_balance: int, user_total_bets: int = 0) -> Tuple[bool, str]:
        if amount <= 0:
            return False, "❌ Ставка должна быть положительным числом"
        if amount < CONFIG.MIN_BET:
            return False, f"❌ Минимальная ставка: {CONFIG.MIN_BET}"
        if amount > CONFIG.MAX_BET:
            return False, f"❌ Максимальная ставка: {CONFIG.MAX_BET}"
        if amount > user_balance:
            return False, f"❌ Недостаточно средств. Баланс: {user_balance}"
        if user_total_bets + amount > CONFIG.MAX_TOTAL_BETS_PER_USER:
            return False, "❌ Превышен лимит ставок"
        return True, ""


class BetParser:
    COLOR_MAP = {
        'к': 'красное', 'кр': 'красное', 'крас': 'красное', 'red': 'красное',
        'ч': 'черное', 'чер': 'черное', 'black': 'черное',
        'з': 'зеленое', 'зел': 'зеленое', 'green': 'зеленое', '0': 'зеленое'
    }
    GROUP_MAP = {
        '1-3': '1-3', '13': '1-3',
        '4-6': '4-6', '46': '4-6',
        '7-9': '7-9', '79': '7-9',
        '10-12': '10-12', '1012': '10-12'
    }

    AMOUNT_PATTERN = re.compile(r"^(\d+)(k|к)?$", re.IGNORECASE)
    MULTIPLE_BETS_PATTERN = re.compile(r'[,и]+\s*')
    CLEAN_PATTERN = re.compile(r'\s+на\s+')

    @staticmethod
    def parse_amount(raw: str) -> Optional[int]:
        if not raw:
            return None
        text = raw.strip().lower().replace(" ", "")
        match = BetParser.AMOUNT_PATTERN.match(text)
        if not match:
            return None
        value = int(match.group(1))
        return value * 1000 if match.group(2) else value

    @staticmethod
    def parse_single_bet(text: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        if not text:
            return None, None, None
        text = ' '.join(text.strip().split())
        parts = text.lower().split()
        if len(parts) < 2:
            return None, None, None
        amount = BetParser.parse_amount(parts[0])
        if amount is None:
            return None, None, None
        target = ' '.join(parts[1:])
        if target in BetParser.COLOR_MAP:
            return amount, "цвет", BetParser.COLOR_MAP[target]
        if target.isdigit() and 0 <= int(target) <= 12:
            return amount, "число", int(target)
        if target in BetParser.GROUP_MAP:
            return amount, "группа", BetParser.GROUP_MAP[target]
        if '-' in target:
            try:
                start, end = map(int, target.split('-'))
                # ПРОВЕРКА: Запрещаем некорректные диапазоны
                if 0 <= start <= 12 and 0 <= end <= 12 and start < end:  # Изменено на строгое неравенство
                    return amount, "группа", f"{start}-{end}"
            except (ValueError, TypeError):
                pass
        return None, None, None

    @staticmethod
    def parse_multiple_bets(text: str) -> List[Tuple[int, str, str]]:
        text = BetParser.CLEAN_PATTERN.sub(' ', text.lower())
        bets = []
        single_bet = BetParser.parse_single_bet(text)
        if all(single_bet):
            bets.append(single_bet)
            return bets
        parts = BetParser.MULTIPLE_BETS_PATTERN.split(text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            bet_data = BetParser.parse_single_bet(part)
            if all(bet_data):
                bets.append(bet_data)
        return bets