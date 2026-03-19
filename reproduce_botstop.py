from aiogram import types
from unittest.mock import MagicMock

class SimpleBotStopHandler:
    def __init__(self):
        self.allowed_commands = [
            'start', 'help', 'menu', 'profile', 'settings', 'профиль',
            'рулетка', 'донат', 'подарки', 'магазин', 'ссылки', 'баланс',
            'топ', 'перевод', 'кража', 'полиция', 'вор', 'ищи', '!бот ищи', 'бот ищи', 'ботищи', 'кубик'
        ]

    def is_command_message(self, message: types.Message) -> bool:
        if not message.text:
            return False

        text = message.text.lower().strip()

        # Проверяем команды с префиксами
        if text.startswith('/'):
            command = text[1:].split('@')[0].split()[0]
            if command in self.allowed_commands:
                return True

        # Проверяем текстовые команды
        for cmd in self.allowed_commands:
            if text.startswith(cmd) or cmd in text: # <--- The suspicious line
                print(f"Matched command: '{cmd}' in text")
                return True

        return False

def test_bypass():
    handler = SimpleBotStopHandler()
    
    # Message that should be blocked (no command)
    msg1 = MagicMock()
    msg1.text = "привет как дела"
    print(f"Message: '{msg1.text}' -> Is Command? {handler.is_command_message(msg1)}") # Expected False
    
    # Message that bypasses block because it contains "вор" (thief)
    msg2 = MagicMock()
    msg2.text = "я сегодня говорил про вор" # "вор" is in allowed_commands
    print(f"Message: '{msg2.text}' -> Is Command? {handler.is_command_message(msg2)}") # Expected True (Bypass)

    # Message that bypasses block because it contains "топ"
    msg3 = MagicMock()
    msg3.text = "это полный топ чувак" 
    print(f"Message: '{msg3.text}' -> Is Command? {handler.is_command_message(msg3)}") # Expected True (Bypass)

    # The user's example "тестл1 тест2 фцв" doesn't seem to match any command though...
    # Unless "тест" matches? No.
    # Maybe "фцв" matches something? No.
    # Wait, check "start", "help" etc. 
    # Maybe user wrote something else in reality.
    
    # Let's check "перевод"
    msg4 = MagicMock()
    msg4.text = "сделай перевод средств"
    print(f"Message: '{msg4.text}' -> Is Command? {handler.is_command_message(msg4)}")

test_bypass()
