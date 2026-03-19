#handlers/roulette/models.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any

from .config import CONFIG


@dataclass
class Bet:
    amount: int
    type: str
    value: Any
    username: str
    user_id: int
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def __str__(self) -> str:
        return f"{self.amount} на {self.value} ({self.type})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount": self.amount,
            "type": self.type,
            "value": self.value,
            "username": self.username,
            "user_id": self.user_id,
            "timestamp": self.timestamp.isoformat()
        }

    def is_same_bet(self, other_bet: 'Bet') -> bool:
        return self.type == other_bet.type and self.value == other_bet.value


class UserBetSession:
    __slots__ = ('user_id', 'username', 'bets', 'total_amount', 'last_update', 'bet_message_ids')

    def __init__(self, user_id: int, username: str):
        self.user_id = user_id
        self.username = username
        self.bets: List[Bet] = []
        self.total_amount = 0
        self.last_update = datetime.now()
        self.bet_message_ids: List[int] = []

    def add_bet(self, bet: Bet) -> bool:
        for existing_bet in self.bets:
            if existing_bet.is_same_bet(bet):
                existing_bet.amount += bet.amount
                self.total_amount += bet.amount
                self.last_update = datetime.now()
                return True
        self.bets.append(bet)
        self.total_amount += bet.amount
        self.last_update = datetime.now()
        return True

    def clear_bets(self) -> int:
        total = self.total_amount
        self.bets.clear()
        self.total_amount = 0
        self.last_update = datetime.now()
        return total

    @property
    def has_bets(self) -> bool:
        return bool(self.bets)

    def get_bets_info(self) -> str:
        if not self.bets:
            return "Нет активных ставок"
        lines = []
        for bet in self.bets:
            plain_name = bet.username  # formatter moved to handlers/utils
            lines.append(f"{plain_name} {bet.amount} на {bet.value}")
        lines.append(f"💰 Общая сумма: {self.total_amount}")
        return "\n".join(lines)


class ChatSession:
    __slots__ = ('chat_id', 'user_sessions', 'waiting_for_bet', 'last_user_bets',
                 'created_at', 'last_spin', 'spin_message_id', 'game_logs',
                 'is_doubling_operation', 'is_spinning', 'spin_lock', 'spin_timer')

    def __init__(self, chat_id: int):
        import asyncio
        self.chat_id = chat_id
        self.user_sessions: Dict[int, UserBetSession] = {}
        self.waiting_for_bet: Dict[int, Tuple[str, str]] = {}
        self.last_user_bets: Dict[int, List[Tuple]] = {}
        self.created_at = datetime.now()
        self.last_spin = None
        self.spin_message_id: Optional[int] = None
        self.game_logs: List[Dict] = []
        self.is_doubling_operation = False
        self.is_spinning = False
        self.spin_lock = asyncio.Lock()
        self.spin_timer: Optional[int] = None  # Для хранения времени кручения

    def get_user_session(self, user_id: int, username: str) -> UserBetSession:
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = UserBetSession(user_id, username)
        else:
            self.user_sessions[user_id].username = username
        return self.user_sessions[user_id]

    def clear_user_session(self, user_id: int) -> int:
        if user_id in self.user_sessions:
            session = self.user_sessions[user_id]
            total = session.total_amount
            del self.user_sessions[user_id]
            return total
        return 0

    @property
    def active_users(self) -> Dict[int, UserBetSession]:
        return {uid: session for uid, session in self.user_sessions.items() if session.has_bets}


class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, ChatSession] = {}

    def get_session(self, chat_id: int) -> ChatSession:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = ChatSession(chat_id)
        return self.sessions[chat_id]

    def cleanup_old_sessions(self, max_age_hours: int = 24):
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        old_chats = [
            chat_id for chat_id, session in self.sessions.items()
            if session.created_at.timestamp() < cutoff_time and not session.active_users
        ]
        for chat_id in old_chats:
            del self.sessions[chat_id]