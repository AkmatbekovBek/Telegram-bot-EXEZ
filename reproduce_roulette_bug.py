import asyncio
from unittest.mock import MagicMock
import sys

# Add project root to path
sys.path.append(r"c:\RouletteBotTelegram")

# Mock classes to simulate the bot's data structures
class MockBet:
    def __init__(self, amount, type, value):
        self.amount = amount
        self.type = type
        self.value = value

class MockGame:
    def get_multiplier(self, type, value):
        if type == "число": return 12
        return 2

    def check_bet(self, type, value, result):
        if type == "число" and value == result: return True
        return False

# Import relevant functions from utils if possible, or mock them closely
# Since we need to test the logic inside handlers.py, we really want to isolate _process_user_results logic.
# However, that method is huge and coupled to DB. 
# We can reproduce the LOGIC flaw by just essentially copying the snippet or creating a simplified test.

def test_logic_flaw():
    print("--- Testing Logic Flaw ---")
    
    # Scenario: User bets 50000 on "0" (number). Result is 0.
    bet = MockBet(50000, "число", 0) # Note: value is int 0
    result = 0
    
    # Logic from handlers.py lines 813-840:
    
    # 1. is_green_result
    is_green_result = (result == 0)
    print(f"is_green_result: {is_green_result}")
    
    # 2. is_green_bet
    # line 824: is_green_bet = bet.type == "цвет" and bet.value == "зеленое"
    is_green_bet = (bet.type == "цвет" and bet.value == "зеленое")
    print(f"is_green_bet: {is_green_bet}")
    
    # 3. net_profit check (simulating calculate_bet_result)
    # utils.py line 131: if result == 0...
    # But wait, calculate_bet_result considers check_bet too.
    # If type="число", value=0, result=0 -> Win!
    # calculate_bet_result logic for 0:
    # It goes to line 131 (if result == 0)
    # line 134: if bet.type == "цвет" and bet.value == "зеленое": ...
    # else: (line 141) -> Refund 50%!
    
    # WAIT! There is a logic error in `utils.py` too!
    
    print("\n[Analysis of utils.py logic]")
    # Looking at utils.py:
    # 131: if result == 0:
    # 134:     if bet.type == "цвет" and bet.value == "зеленое": match -> win 12x
    # 141:     else: refund 50%
    
    # So if I bet on NUMBER 0 (type="число", value=0), it goes to else -> Refund 50%
    # This is WRONG! It should check if the bet ITSELF won on 0.
    
    if is_green_result:
        if bet.type == "цвет" and bet.value == "зеленое":
            print("Result: WON (Green Color)")
        else:
             # The flaw: utils.py assumes ANY non-green-color bet loses on 0
             # But if the bet was on Number 0, it should WIN.
             print("Result: REFUND 50% (Flaw!)")

test_logic_flaw()
