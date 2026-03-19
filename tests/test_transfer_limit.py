import sys
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

from handlers.transfer_limit import TransferLimit

class TestTransferLimit(unittest.TestCase):
    def setUp(self):
        self.limit = TransferLimit()
        self.limit.MAX_LIMIT = 1000  # Smaller limit for testing
        self.limit.LIMIT_PERIOD_HOURS = 6

    @patch('handlers.transfer_limit.ShopRepository')
    @patch('handlers.transfer_limit.TransferLimitRepository')
    @patch('handlers.transfer_limit.get_db')
    def test_limit_enforcement(self, mock_get_db, mock_limit_repo, mock_shop_repo):
        # Mock DB session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # 1. Test regular user with no history
        mock_shop_repo.get_user_purchases.return_value = [] # No unlimited
        mock_limit_repo.get_user_transfers_last_6h.return_value = [] # No transfers

        can_transfer, _, remaining, is_unlimited = self.limit.can_make_transfer(1, 500)
        self.assertTrue(can_transfer)
        self.assertEqual(remaining, 1000)
        self.assertFalse(is_unlimited)

        # 2. Test user nearing limit
        # Simulate previous transfers totaling 800
        mock_transfer1 = MagicMock()
        mock_transfer1.amount = 800
        mock_limit_repo.get_user_transfers_last_6h.return_value = [mock_transfer1]

        can_transfer, _, remaining, is_unlimited = self.limit.can_make_transfer(1, 100)
        self.assertTrue(can_transfer)
        self.assertEqual(remaining, 200) # 1000 - 800 = 200. NOT 100. remaining limit is calculated from TOTAL history.

        # 3. Test user exceeding limit
        can_transfer, _, remaining, is_unlimited = self.limit.can_make_transfer(1, 300)
        self.assertFalse(can_transfer) # 800 + 300 = 1100 > 1000
        self.assertEqual(remaining, 200)

        # 4. Test unlimited user
        mock_shop_repo.get_user_purchases.return_value = [3] # Has item 3 (unlimited)
        
        can_transfer, _, remaining, is_unlimited = self.limit.can_make_transfer(1, 999999)
        self.assertTrue(can_transfer)
        self.assertTrue(is_unlimited)

if __name__ == '__main__':
    unittest.main()
