# handlers/roulette/config.py
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Tuple, Optional

# Импортируем state manager
from .state_manager import state_manager


@dataclass(frozen=True)
class RouletteConfig:
    MIN_BET: int = 1000
    MAX_BET: int = 100_000_000_000_000_000_000
    MAX_TOTAL_BETS_PER_USER: int = 100_000_000_000_000_000_000
    SPIN_DELAY: int = 3
    MAX_GAME_LOGS: int = 26
    MIN_SPIN_INTERVAL: int = 3
    MAX_SPINS_PER_MINUTE: int = 10
    RESET_INTERVAL: int = 60
    CLEANUP_INTERVAL: int = 300
    NUMBERS: Tuple[int, ...] = tuple(range(0, 13))
    RED_NUMBERS: frozenset = frozenset({1, 3, 5, 7, 9, 11})
    BLACK_NUMBERS: frozenset = frozenset({2, 4, 6, 8, 10, 12})
    PAYOUTS: Optional[Dict[str, Decimal]] = field(default_factory=lambda: {
        "число": Decimal('12.0'),
        "цвет_красное": Decimal('2.0'),
        "цвет_черное": Decimal('2.0'),
        "цвет_зеленое": Decimal('12.0'),
        "группа_стандарт": Decimal('4.333')
    })

    @classmethod
    def is_roulette_enabled(cls, chat_id: int) -> bool:
        """Проверяет, включена ли рулетка в чате"""
        return state_manager.is_roulette_enabled(chat_id)


CONFIG = RouletteConfig()