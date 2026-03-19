import pytz
from datetime import datetime

from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, Float, Text, ForeignKey, Enum as SQLEnum, Date, \
    UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.sql.sqltypes import Numeric

from enum import Enum

from database import Base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, BigInteger, Text, Float, Index


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    reference_link = Column(Text)
    coins = Column(Numeric(30, 0), default=5000)
    win_coins = Column(Numeric(30, 0), default=0)
    defeat_coins = Column(Numeric(30, 0), default=0)  # до 30 цифр
    max_win_coins = Column(Numeric(30, 0), default=0)
    min_win_coins = Column(Numeric(30, 0), default=0)
    max_bet = Column(Numeric(30, 0), default=0)
    is_admin = Column(Boolean, default=False)
    win_games = Column(Integer, default=0, nullable=False)
    lose_games = Column(Integer, default=0, nullable=False)

    # ИСПРАВЛЕННЫЕ СТОЛБЦЫ (убраны дубли):
    robberies_today = Column(Integer, default=0, nullable=False)
    last_robbery_reset = Column(DateTime(timezone=True), nullable=True)
    action = Column(String(50), nullable=True)  # Изменено на nullable=True
    duration_minutes = Column(Integer, default=0, nullable=False)  # Изменено на default=0

    # Статусы (уже должны быть):
    status_text = Column(String(200), nullable=True)
    status_changed_at = Column(DateTime(timezone=True), nullable=True)

    # ДОБАВЬТЕ ЭТИ ПОЛЯ ДЛЯ НИКНЕЙМОВ:
    nickname = Column(String(32), nullable=True, unique=True)  # Уникальный никнейм
    nickname_changed_at = Column(DateTime(timezone=True), nullable=True)  # Время изменения никнейма

    # Связи
    references = relationship("ReferenceUser", back_populates="owner")
    transactions_from = relationship("Transaction", foreign_keys="Transaction.from_user_id", back_populates="from_user")
    transactions_to = relationship("Transaction", foreign_keys="Transaction.to_user_id", back_populates="to_user")
    chat_memberships = relationship("UserChat", back_populates="user")
    daily_records = relationship("DailyRecord", back_populates="user")
    roulette_transactions = relationship("RouletteTransaction", back_populates="user")
    purchases = relationship("UserPurchase", back_populates="user")
    transfer_limits = relationship("TransferLimit", back_populates="user")
    gifts = relationship("UserGift", backref="user")


class ReferenceUser(Base):
    __tablename__ = "reference_users"

    id = Column(Integer, primary_key=True)
    owner_telegram_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    reference_telegram_id = Column(BigInteger, nullable=False)

    # Связи
    owner = relationship("TelegramUser", back_populates="references")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    from_user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))  # Изменено на BigInteger
    to_user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))    # Изменено на BigInteger
    amount = Column(Numeric, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    description = Column(Text)

    # Связи
    from_user = relationship("TelegramUser", foreign_keys=[from_user_id], back_populates="transactions_from")
    to_user = relationship("TelegramUser", foreign_keys=[to_user_id], back_populates="transactions_to")

class UserChat(Base):
    __tablename__ = "user_chats"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    chat_id = Column(BigInteger, nullable=False)

    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser", back_populates="chat_memberships")


class DailyRecord(Base):
    __tablename__ = "daily_records"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    username = Column(Text, nullable=False)
    first_name = Column(Text)
    amount = Column(Numeric, nullable=False)
    record_date = Column(Date, nullable=False)
    chat_id = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser", back_populates="daily_records")

# database/models.py (добавить в конец файла)

class DailyLossRecord(Base):
    """Таблица для рекордов проигрышей за день"""
    __tablename__ = 'daily_loss_records'

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False)
    username = Column(Text, nullable=False)
    first_name = Column(Text)
    amount = Column(Numeric, nullable=False)  # Сумма проигрыша (положительное число)
    record_date = Column(Date, nullable=False)
    chat_id = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser")

    def __repr__(self):
        return f"<DailyLossRecord(user_id={self.user_id}, amount={self.amount}, date={self.record_date})>"


class RouletteTransaction(Base):
    __tablename__ = "roulette_transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    amount = Column(Numeric, nullable=False)
    is_win = Column(Boolean, nullable=False)
    bet_type = Column(Text)
    bet_value = Column(Text)
    result_number = Column(BigInteger)
    profit = Column(Numeric)
    game_session_id = Column(String(100), nullable=True, index=True)  # ДОБАВЛЕНО ДЛЯ ГРУППИРОВКИ
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser", back_populates="roulette_transactions")


class RouletteGameLog(Base):
    __tablename__ = "roulette_game_logs"

    id = Column(BigInteger, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    result = Column(BigInteger, nullable=False)
    color_emoji = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserPurchase(Base):
    __tablename__ = "user_purchases"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    item_id = Column(BigInteger, nullable=False)
    item_name = Column(Text, nullable=False)
    price = Column(BigInteger, nullable=False)
    chat_id = Column(Numeric, nullable=False, default=-1)
    purchased_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_user_item', 'user_id', 'item_id'),
    )
    # Связи
    user = relationship("TelegramUser", back_populates="purchases")


class TransferLimit(Base):
    __tablename__ = "transfer_limits"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"))
    amount = Column(BigInteger(), nullable=False)
    transfer_time = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    user = relationship("TelegramUser", back_populates="transfer_limits")


# Добавьте эти модели в конец файла models.py

class Gift(Base):
    __tablename__ = "gifts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    sticker = Column(String(50), nullable=False)  # ID стикера или эмодзи
    price = Column(Integer, nullable=False)
    compliment = Column(Text, nullable=False)  # Комплимент при дарении
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserGift(Base):
    __tablename__ = "user_gifts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False)  # Изменено на BigInteger
    gift_id = Column(Integer, ForeignKey("gifts.id"), nullable=False)
    quantity = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    gift = relationship("Gift")

class RouletteLimit(Base):
    __tablename__ = "roulette_limits"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False)
    chat_id = Column(BigInteger, nullable=False)  # ID чата/группы
    date = Column(Date, nullable=False)
    spin_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    user = relationship("TelegramUser")

    # Уникальный индекс на user_id, chat_id и date
    __table_args__ = (UniqueConstraint('user_id', 'chat_id', 'date', name='_user_chat_date_uc'),)


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=True)
    chat_type = Column(String(50), nullable=True)  # 'group', 'supergroup', 'channel'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BotStop(Base):
    __tablename__ = 'bot_stop_users'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    blocked_user_id = Column(BigInteger, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

    # Уникальный индекс, чтобы нельзя было заблокировать одного пользователя несколько раз
    __table_args__ = (
        UniqueConstraint('user_id', 'blocked_user_id', name='unique_user_block'),
    )

    def __repr__(self):
        return f"<BotStop(user_id={self.user_id}, blocked_user_id={self.blocked_user_id})>"


# database/models.py (с другими именами таблиц)
class UserChatSearch(Base):
    __tablename__ = 'user_chats_search'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    chat_title = Column(String(255), nullable=True)  # ИЗМЕНИТЕ НА nullable=True
    created_at = Column(DateTime, default=datetime.now)
    last_activity = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'chat_id', name='unique_user_chat_search'),
    )


class UserNickSearch(Base):
    __tablename__ = 'user_nicks_search'  # ← ИЗМЕНИТЕ ИМЯ

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    nick = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('user_id', 'nick', name='unique_user_nick_search'),
    )

# database/models.py (добавьте в конец файла)
class ThiefArrest(Base):
    __tablename__ = 'thief_arrests'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    release_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<ThiefArrest(user_id={self.user_id}, release_time={self.release_time})>"


class StealAttempt(Base):
    __tablename__ = 'steal_attempts'

    id = Column(Integer, primary_key=True)
    thief_id = Column(BigInteger, nullable=False, index=True)
    victim_id = Column(BigInteger, nullable=False, index=True)
    successful = Column(Boolean, nullable=False)
    amount = Column(BigInteger, default=0)
    attempt_time = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<StealAttempt(thief_id={self.thief_id}, successful={self.successful}, amount={self.amount})>"


# database/models.py (добавьте в конец файла)
class DonatePurchase(Base):
    __tablename__ = 'donate_purchases'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    item_id = Column(Integer, nullable=False)  # 1 - Вор в законе, 2 - Полицейский, 3 - Снятие лимита
    item_name = Column(String(255), nullable=False)
    purchase_date = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=True)  # null = навсегда

    __table_args__ = (
        UniqueConstraint('user_id', 'item_id', name='unique_user_item'),
    )

    def is_active(self):
        """Проверяет, активна ли покупка"""
        if self.expires_at is None:  # Навсегда
            return True
        return datetime.now() < self.expires_at

    def __repr__(self):
        return f"<DonatePurchase(user_id={self.user_id}, item='{self.item_name}')>"

class UserArrest(Base):
    __tablename__ = 'user_arrests'

    user_id = Column(BigInteger, primary_key=True)
    arrested_by = Column(BigInteger, nullable=False)
    release_time = Column(DateTime, nullable=False)
    arrested_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<UserArrest(user_id={self.user_id}, arrested_by={self.arrested_by}, release_time={self.release_time})>"


class Marriage(Base):
    __tablename__ = 'marriages'

    id = Column(Integer, primary_key=True)
    user1 = Column(BigInteger, nullable=False)
    user2 = Column(BigInteger, nullable=False)
    married_at = Column(DateTime, default=datetime.utcnow)
    chat_id = Column(BigInteger, nullable=False)

    def __repr__(self):
        return f"<Marriage(user1={self.user1}, user2={self.user2}, married_at={self.married_at})>"



class DivorceRequest(Base):
    __tablename__ = "divorce_requests"

    id = Column(Integer, primary_key=True)
    requester = Column(BigInteger, nullable=False)
    partner = Column(BigInteger, nullable=False)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<DivorceRequest(requester={self.requester}, partner={self.partner})>"


class ModerationAction(str, Enum):
    MUTE = "mute"
    BAN = "ban"
    KICK = "kick"


class ModerationLog(Base):
    __tablename__ = "moderation_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(SQLEnum(ModerationAction), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    admin_id = Column(BigInteger, nullable=False)
    reason = Column(String, default="")
    duration_minutes = Column(Integer, nullable=True)  # только для mute
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, index=True)
    chat_id = Column(BigInteger, index=True)
    username = Column(String)
    coins = Column(Integer, default=0)
    win_coins = Column(Integer, default=0)
    defeat_coins = Column(Integer, default=0)
    max_win_coins = Column(Integer, default=0)
    min_win_coins = Column(Integer, default=0)   # ← важно: default=0, не NULL
    max_bet_coins = Column(Integer, default=0)
    status_text = Column(String(200), nullable=True)  # Текст статуса
    status_changed_at = Column(DateTime, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    message_id = Column(BigInteger, nullable=False)
    text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Индексы для быстрого поиска
    __table_args__ = (
        Index('idx_chat_created', 'chat_id', 'created_at'),
        Index('idx_user_chat_date', 'user_id', 'chat_id', 'created_at'),
        Index('idx_chat_user_date', 'chat_id', 'user_id', 'created_at'),
    )

    # Связь с пользователем
    user = relationship("TelegramUser")



class GroupInvite(Base):
    """Таблица для отслеживания приглашенных пользователей в группы"""
    __tablename__ = 'group_invites'

    id = Column(Integer, primary_key=True)
    inviter_id = Column(BigInteger, nullable=False, index=True)  # Кто пригласил
    invited_id = Column(BigInteger, nullable=False, index=True)  # Кого пригласили
    chat_id = Column(BigInteger, nullable=False, index=True)  # В какую группу
    invited_at = Column(DateTime, default=datetime.now)

    # Уникальный индекс: один пользователь может быть приглашен только один раз в конкретную группу
    __table_args__ = (
        UniqueConstraint('invited_id', 'chat_id', name='unique_invited_in_chat'),
    )

    def __repr__(self):
        return f"<GroupInvite(inviter={self.inviter_id}, invited={self.invited_id}, chat={self.chat_id})>"


class ActiveRouletteBet(Base):
    """Таблица для хранения активных ставок рулетки (для возврата при сбоях)"""
    __tablename__ = 'active_roulette_bets'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    amount = Column(BigInteger, nullable=False)
    bet_type = Column(String(50), nullable=False)
    bet_value = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<ActiveRouletteBet(user_id={self.user_id}, amount={self.amount}, value={self.bet_value})>"


class Raffle(Base):
    __tablename__ = 'raffles'
    
    id = Column(String(50), primary_key=True)  # raffle_timestamp_random
    chat_id = Column(BigInteger, nullable=False, index=True)
    creator_id = Column(BigInteger, nullable=False)
    creator_name = Column(String(255))
    amount = Column(BigInteger, nullable=False)
    status = Column(String(20), default='waiting')  # waiting, active, finished, cancelled
    created_at = Column(DateTime, default=datetime.now)
    message_id = Column(Integer, nullable=True)
    winners_count = Column(Integer, default=1)
    
    participants = relationship("RaffleParticipant", back_populates="raffle", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Raffle(id={self.id}, amount={self.amount}, status={self.status})>"


class RaffleParticipant(Base):
    __tablename__ = 'raffle_participants'
    
    id = Column(Integer, primary_key=True)
    raffle_id = Column(String(50), ForeignKey('raffles.id'), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(255))
    tickets = Column(Integer, default=1)
    joined_at = Column(DateTime, default=datetime.now)
    
    raffle = relationship("Raffle", back_populates="participants")

    def __repr__(self):
        return f"<RaffleParticipant(user={self.user_id}, raffle={self.raffle_id})>"