import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Setup path
sys.path.append(r"c:\RouletteBotTelegram")

# Mock modules to prevent import errors
sys.modules['database'] = MagicMock()
sys.modules['database.models'] = MagicMock()
sys.modules['database.crud'] = MagicMock()

# Mock handlers that have complex dependencies
sys.modules['handlers.admin.mute_ban'] = MagicMock()
sys.modules['handlers.cleanup_scheduler'] = MagicMock()
sys.modules['handlers.admin.admin_notifications'] = MagicMock()
sys.modules['handlers.admin.status'] = MagicMock()
sys.modules['handlers.record'] = MagicMock()
sys.modules['handlers.record.record_core'] = MagicMock()
sys.modules['handlers.record.services'] = MagicMock()

# Now import
from handlers.admin.main_admin_handler import AdminHandler

class TestAdminProtectionCommands(unittest.IsolatedAsyncioTestCase):
    async def test_give_protection_search(self):
        print("\nTesting: give_protection search")
        handler = AdminHandler()
        
        message = MagicMock()
        message.from_user.id = 1
        message.get_args.return_value = "12345 search 30"
        message.answer = AsyncMock()
        message.bot = MagicMock()
        
        # Mock checks
        with patch('handlers.admin.main_admin_handler.check_admin_async', AsyncMock(return_value=True)):
            with patch('handlers.admin.main_admin_handler.db_session') as mock_session:
                # Mock DB behavior
                db = MagicMock()
                mock_session.return_value.__enter__.return_value = db
                
                # Mock Repositories
                from database.crud import UserRepository, ShopRepository
                UserRepository.get_user_by_telegram_id.return_value = MagicMock(first_name="TestUser")
                ShopRepository.get_user_purchases.return_value = [] 
                
                await handler.give_protection(message)
                
                # Search ID = 4
                ShopRepository.add_user_purchase.assert_called_with(
                    db=db,
                    user_id=12345,
                    item_id=4,
                    item_name="🛡️ Защита от поиска",
                    price=0,
                    chat_id=-1,
                    duration_days=30
                )
                print("[PASS] Added search protection")

    async def test_give_protection_stop(self):
        print("\nTesting: give_protection stop")
        handler = AdminHandler()
        
        message = MagicMock()
        message.get_args.return_value = "12345 stop 30"
        message.answer = AsyncMock()
        message.bot = MagicMock() # Needed for notification

        with patch('handlers.admin.main_admin_handler.check_admin_async', AsyncMock(return_value=True)):
            with patch('handlers.admin.main_admin_handler.db_session') as mock_session:
                db = MagicMock()
                mock_session.return_value.__enter__.return_value = db
                
                from database.crud import ShopRepository
                ShopRepository.get_user_purchases.return_value = []
                
                await handler.give_protection(message)
                
                # Stop ID = 5
                ShopRepository.add_user_purchase.assert_called_with(
                    db=db,
                    user_id=12345,
                    item_id=5, 
                    item_name="🛡️ Защита от бот стоп",
                    price=0,
                    chat_id=-1,
                    duration_days=30
                )
                print("[PASS] Added stop protection")

    async def test_remove_protection(self):
        print("\nTesting: remove_protection full")
        handler = AdminHandler()
        
        message = MagicMock()
        message.get_args.return_value = "12345 full"
        message.answer = AsyncMock()
        
        with patch('handlers.admin.main_admin_handler.check_admin_async', AsyncMock(return_value=True)):
            with patch('handlers.admin.main_admin_handler.db_session') as mock_session:
                db = MagicMock()
                mock_session.return_value.__enter__.return_value = db
                
                from database.crud import ShopRepository
                # Mock that user HAS the protection
                ShopRepository.get_user_purchases.return_value = [6] # Full ID = 6
                
                await handler.remove_protection(message)
                
                ShopRepository.remove_user_purchase.assert_called_with(db, 12345, 6)
                print("[PASS] Removed full protection")

if __name__ == '__main__':
    unittest.main()
