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
            # FIXED LOGIC
            if text == cmd or text.startswith(cmd + " "):
                return True
        return False

def test_fix():
    handler = SimpleBotStopHandler()
    
    print("--- Testing Fix ---")
    
    # 1. Valid command
    msg1 = MagicMock()
    msg1.text = "топ"
    print(f"'{msg1.text}' -> Allowed? {handler.is_command_message(msg1)} (Expect True)")
    
    # 2. Valid command with arg
    msg2 = MagicMock()
    msg2.text = "вор user"
    print(f"'{msg2.text}' -> Allowed? {handler.is_command_message(msg2)} (Expect True)")
    
    # 3. Message containing command word (Attack)
    msg3 = MagicMock()
    msg3.text = "ты полный вор и дурак" # Contains "вор"
    print(f"'{msg3.text}' -> Allowed? {handler.is_command_message(msg3)} (Expect False - Blocked)")

    # 4. User example
    msg4 = MagicMock()
    msg4.text = "тестл1 тест2 фцв"
    print(f"'{msg4.text}' -> Allowed? {handler.is_command_message(msg4)} (Expect False - Blocked)")

    # 5. User example 2
    msg5 = MagicMock()
    msg5.text = "23423 ва пвапвалд 345одлп"
    print(f"'{msg5.text}' -> Allowed? {handler.is_command_message(msg5)} (Expect False - Blocked)")

test_fix()
