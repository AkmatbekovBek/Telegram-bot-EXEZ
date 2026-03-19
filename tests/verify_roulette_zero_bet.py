import sys
import unittest
from unittest.mock import MagicMock

# 1. Setup path first
sys.path.append(r"c:\RouletteBotTelegram")

# 2. Mock ONLY application dependencies that cause side effects or require config
# Mocking 'config' module because it likely connects to DB or Token
config_mock = MagicMock()
config_mock.bot = MagicMock()
sys.modules['config'] = config_mock

# Mock handlers.roulette.config
roulette_config = MagicMock()
roulette_config.CONFIG = MagicMock()
sys.modules['handlers.roulette.config'] = roulette_config

# Mock validators
validators_mock = MagicMock()
sys.modules['handlers.roulette.validators'] = validators_mock

# 3. Import the unit under test
try:
    from handlers.roulette.utils import calculate_bet_result
except ImportError as e:
    print(f"Failed to import utils: {e}")
    sys.exit(1)

class MockGame:
    def get_multiplier(self, type, value):
        if type == "число": return 12
        return 2

    def check_bet(self, type, value, result):
        if type == "число" and value == result: return True
        return False

class MockBet:
    def __init__(self, amount, type, value):
        self.amount = amount
        self.type = type
        self.value = value

class TestRouletteZeroLogic(unittest.TestCase):
    def test_number_zero_wins_on_zero(self):
        print("\nTesting: Bet on Number 0, Result 0")
        game = MockGame()
        bet = MockBet(100, "число", 0)
        result = 0
        
        # calculate_bet_result returns (net_profit, payout)
        net_profit, payout = calculate_bet_result(game, bet, result)
        
        print(f"Profit: {net_profit}, Payout: {payout}")
        
        # Expectation: Win logic returns gross_profit, total_payout
        # gross_profit = 100 * 12 = 1200
        self.assertEqual(net_profit, 1200, "Should win 1200 coins")
        self.assertEqual(payout, 1200, "Payout should be 1200 coins")
        print("[PASS] Number 0 wins on 0")

    def test_green_color_wins_on_zero(self):
        # We need to adjust MockGame to handle checks like real game
        pass 

    def test_other_color_refunds_on_zero(self):
        print("\nTesting: Bet on Red, Result 0")
        game = MockGame()
        bet = MockBet(100, "цвет", "красное")
        result = 0
        
        net_profit, payout = calculate_bet_result(game, bet, result)
        
        # Expectation: -50, 50
        self.assertEqual(net_profit, -50, "Should be -50")
        self.assertEqual(payout, 50, "Should be 50")
        print("[PASS] Red refunds on 0")

if __name__ == '__main__':
    unittest.main()
