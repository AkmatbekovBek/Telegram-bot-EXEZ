#handlers/slot_machine/config.py

# Конфигурация игрового автомата
SLOT_MACHINE_CONFIG = {
    'payouts': {
        'three_sevens': 7,
        'three_bars': 5,
        'three_grapes': 4,
        'three_lemons': 3,
        'two_sevens': 2,
    },
    'bet_min': 10000,
    'bet_max': 100000000,
    'throttle_time': 2  # секунды между играми
}

# Символы игрового автомата
SLOT_SYMBOLS = ["BAR", "🍇", "🍋", "7️⃣"]