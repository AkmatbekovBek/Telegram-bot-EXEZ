import sys
import os
import unittest
from decimal import Decimal

# Add project root to path
sys.path.append(os.getcwd())

from handlers.raffle.raffle import calculate_winners, MIN_PARTICIPANTS, WINNER_PERCENTAGE

class TestRaffleLogic(unittest.TestCase):
    def test_calculate_winners_5_participants(self):
        # 5 participants. 30% = 1.5 -> 1 winner.
        participants = [{'user_id': i, 'username': f'u{i}'} for i in range(5)]
        total_amount = 50000
        
        winners = calculate_winners(participants, total_amount)
        
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]['prize'], 50000)

    def test_calculate_winners_10_participants(self):
        # 10 participants. 30% = 3 winners.
        participants = [{'user_id': i, 'username': f'u{i}'} for i in range(10)]
        total_amount = 60000
        
        # 3 winners, 20000 each
        winners = calculate_winners(participants, total_amount)
        
        self.assertEqual(len(winners), 3)
        for w in winners:
            self.assertEqual(w['prize'], 20000)
    
    def test_calculate_winners_12_participants(self):
        # 12 participants. 30% = 3.6 -> 3 winners (int conversion). user said 30%. usually int() floors.
        # My implementation: int(12 * 0.3) = 3.
        participants = [{'user_id': i, 'username': f'u{i}'} for i in range(12)]
        total_amount = 100000
        
        winners = calculate_winners(participants, total_amount)
        
        self.assertEqual(len(winners), 3)
        # 100000 / 3 = 33333. Remainder 1.
        self.assertEqual(winners[0]['prize'], 33334)
        self.assertEqual(winners[1]['prize'], 33333)
        self.assertEqual(winners[2]['prize'], 33333)

if __name__ == '__main__':
    unittest.main()
