# handlers/donate/manual_payment.py

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import text

from database import get_db

logger = logging.getLogger(__name__)


@dataclass
class ManualPaymentRequest:
    id: int
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    item_type: str  # coins | privilege
    item_id: int
    item_name: str
    coins_amount: int
    price_text: str
    status: str
    created_at: Optional[datetime] = None
    receipt_chat_id: Optional[int] = None
    receipt_message_id: Optional[int] = None
    admin_chat_id: Optional[int] = None
    admin_message_id: Optional[int] = None
    decided_by: Optional[int] = None
    decided_at: Optional[datetime] = None


class ManualPaymentManager:
    """Хранит заявки на ручную оплату и связывает: пользователь -> чек -> проверка админами."""

    def __init__(self):
        self._init_table()

    @contextmanager
    def _db_session(self):
        session = None
        try:
            session = next(get_db())
            yield session
        except Exception as e:
            logger.error(f"Database error in ManualPaymentManager: {e}")
            if session:
                session.rollback()
            raise
        finally:
            if session:
                session.close()

    def _init_table(self):
        with self._db_session() as db:
            try:
                db.execute(text('''
                    CREATE TABLE IF NOT EXISTS manual_payment_requests
                    (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        item_type TEXT NOT NULL,
                        item_id INTEGER NOT NULL,
                        item_name TEXT NOT NULL,
                        coins_amount BIGINT DEFAULT 0,
                        price_text TEXT DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'awaiting_receipt',
                        receipt_chat_id BIGINT,
                        receipt_message_id BIGINT,
                        admin_chat_id BIGINT,
                        admin_message_id BIGINT,
                        decided_by BIGINT,
                        decided_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                '''))

                db.execute(text('''
                    CREATE INDEX IF NOT EXISTS idx_mpr_user_status
                    ON manual_payment_requests (user_id, status)
                '''))
                db.commit()
            except Exception as e:
                logger.error(f"Failed to init manual_payment_requests table: {e}")
                db.rollback()

    def create_request(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        item_type: str,
        item_id: int,
        item_name: str,
        coins_amount: int,
        price_text: str,
    ) -> int:
        """Создает новую заявку и отменяет предыдущие 'awaiting_receipt' заявки пользователя."""
        with self._db_session() as db:
            try:
                db.execute(
                    text("""
                        UPDATE manual_payment_requests
                        SET status='cancelled', updated_at=CURRENT_TIMESTAMP
                        WHERE user_id=:user_id AND status='awaiting_receipt'
                    """),
                    {"user_id": user_id},
                )

                row = db.execute(
                    text("""
                        INSERT INTO manual_payment_requests
                            (user_id, username, first_name, last_name, item_type, item_id, item_name, coins_amount, price_text, status)
                        VALUES
                            (:user_id, :username, :first_name, :last_name, :item_type, :item_id, :item_name, :coins_amount, :price_text, 'awaiting_receipt')
                        RETURNING id
                    """),
                    {
                        "user_id": user_id,
                        "username": username,
                        "first_name": first_name,
                        "last_name": last_name,
                        "item_type": item_type,
                        "item_id": item_id,
                        "item_name": item_name,
                        "coins_amount": coins_amount,
                        "price_text": price_text,
                    },
                ).fetchone()

                db.commit()
                return int(row[0])
            except Exception as e:
                logger.error(f"Failed to create manual payment request: {e}", exc_info=True)
                db.rollback()
                raise

    def get_latest_user_request(self, user_id: int, status: str) -> Optional[ManualPaymentRequest]:
        with self._db_session() as db:
            try:
                row = db.execute(
                    text("""
                        SELECT id, user_id, username, first_name, last_name,
                               item_type, item_id, item_name, coins_amount, price_text,
                               status, created_at, receipt_chat_id, receipt_message_id,
                               admin_chat_id, admin_message_id, decided_by, decided_at
                        FROM manual_payment_requests
                        WHERE user_id=:user_id AND status=:status
                        ORDER BY id DESC
                        LIMIT 1
                    """),
                    {"user_id": user_id, "status": status},
                ).fetchone()
                return self._row_to_request(row) if row else None
            except Exception as e:
                logger.error(f"Failed to get pending manual payment request: {e}")
                return None

    def get_request_by_id(self, request_id: int) -> Optional[ManualPaymentRequest]:
        with self._db_session() as db:
            try:
                row = db.execute(
                    text("""
                        SELECT id, user_id, username, first_name, last_name,
                               item_type, item_id, item_name, coins_amount, price_text,
                               status, created_at, receipt_chat_id, receipt_message_id,
                               admin_chat_id, admin_message_id, decided_by, decided_at
                        FROM manual_payment_requests
                        WHERE id=:id
                    """),
                    {"id": request_id},
                ).fetchone()
                return self._row_to_request(row) if row else None
            except Exception as e:
                logger.error(f"Failed to get manual payment request by id={request_id}: {e}")
                return None

    def attach_receipt(self, request_id: int, receipt_chat_id: int, receipt_message_id: int):
        """Помечает, что чек получен и заявка готова к отправке/проверке."""
        with self._db_session() as db:
            try:
                db.execute(
                    text("""
                        UPDATE manual_payment_requests
                        SET receipt_chat_id=:rcid,
                            receipt_message_id=:rmid,
                            status='pending_admin',
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=:id AND status='awaiting_receipt'
                    """),
                    {"rcid": receipt_chat_id, "rmid": receipt_message_id, "id": request_id},
                )
                db.commit()
            except Exception as e:
                logger.error(f"Failed to attach receipt for request id={request_id}: {e}")
                db.rollback()
                raise

    def set_admin_message(self, request_id: int, admin_chat_id: int, admin_message_id: int):
        with self._db_session() as db:
            try:
                db.execute(
                    text("""
                        UPDATE manual_payment_requests
                        SET admin_chat_id=:acid,
                            admin_message_id=:amid,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=:id
                    """),
                    {"acid": admin_chat_id, "amid": admin_message_id, "id": request_id},
                )
                db.commit()
            except Exception as e:
                logger.error(f"Failed to set admin message for request id={request_id}: {e}")
                db.rollback()

    def cancel_request(self, request_id: int, user_id: int) -> bool:
        with self._db_session() as db:
            try:
                res = db.execute(
                    text("""
                        UPDATE manual_payment_requests
                        SET status='cancelled', updated_at=CURRENT_TIMESTAMP
                        WHERE id=:id AND user_id=:user_id AND status='awaiting_receipt'
                    """),
                    {"id": request_id, "user_id": user_id},
                )
                db.commit()
                return res.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to cancel request id={request_id}: {e}")
                db.rollback()
                return False

    def decide(self, request_id: int, admin_id: int, decision: str) -> bool:
        """decision: approved | rejected"""
        if decision not in {"approved", "rejected"}:
            raise ValueError("Invalid decision")

        with self._db_session() as db:
            try:
                res = db.execute(
                    text("""
                        UPDATE manual_payment_requests
                        SET status=:status,
                            decided_by=:admin_id,
                            decided_at=CURRENT_TIMESTAMP,
                            updated_at=CURRENT_TIMESTAMP
                        WHERE id=:id AND status='pending_admin'
                    """),
                    {"status": decision, "admin_id": admin_id, "id": request_id},
                )
                db.commit()
                return res.rowcount > 0
            except Exception as e:
                logger.error(f"Failed to decide request id={request_id}: {e}")
                db.rollback()
                return False

    @staticmethod
    def _row_to_request(row) -> ManualPaymentRequest:
        return ManualPaymentRequest(
            id=int(row[0]),
            user_id=int(row[1]),
            username=row[2],
            first_name=row[3],
            last_name=row[4],
            item_type=row[5],
            item_id=int(row[6]),
            item_name=row[7],
            coins_amount=int(row[8] or 0),
            price_text=row[9] or "",
            status=row[10],
            created_at=row[11],
            receipt_chat_id=row[12],
            receipt_message_id=row[13],
            admin_chat_id=row[14],
            admin_message_id=row[15],
            decided_by=row[16],
            decided_at=row[17],
        )
