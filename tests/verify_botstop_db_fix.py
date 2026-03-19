import sys
import unittest
from unittest.mock import MagicMock
import io

# Force UTF-8 for stdout to avoid cp1251 errors
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Mock system encoding
sys.path.append(r"c:\RouletteBotTelegram")

# Setup Mocks
database_mock = MagicMock()
sys.modules['database'] = database_mock
models_mock = MagicMock()
sys.modules['database.models'] = models_mock
database_mock.models = models_mock

# Mock BotStop Model correctly for SQLAlchemy query building
class MockColumn:
    def __eq__(self, other): return True

class MockBotStopModel:
    user_id = MockColumn()
    blocked_user_id = MockColumn()
    def __init__(self, user_id, blocked_user_id, created_at):
        self.user_id = user_id
        self.blocked_user_id = blocked_user_id
        self.created_at = created_at

models_mock.BotStop = MockBotStopModel

# Import unit under test
from database.crud import BotStopRepository
from sqlalchemy.exc import IntegrityError

# Mock Session
class MockSession:
    def __init__(self):
        self.added = []
        self.repaired = False
        self._query = MagicMock()
        
    def query(self, *args):
        # Return none for first check
        self._query.filter.return_value.first.return_value = None
        return self._query

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        if not self.repaired and self.added:
            raise IntegrityError("duplicate key value violates unique constraint", "params", "orig")
    
    def rollback(self): pass
    
    def execute(self, cmd):
        if "setval" in str(cmd):
            self.repaired = True

def test_fix():
    print("Testing BotStopRepository resilience...")
    db = MockSession()
    
    try:
        res = BotStopRepository.create_block_record(db, 1, 2)
        if db.repaired and res:
            print("✅ SUCCESS: Error caught, sequence repaired, record created.")
        else:
            print(f"❌ FAILED: Repaired={db.repaired}, Result={res}")
    except Exception as e:
        print(f"❌ CRASHED: {e}")

if __name__ == "__main__":
    test_fix()
