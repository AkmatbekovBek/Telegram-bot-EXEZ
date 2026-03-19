import unittest
from unittest.mock import MagicMock, AsyncMock
from aiogram import types
import asyncio
import sys
import os

# Add project root to path
sys.path.append(r"c:\RouletteBotTelegram")

from handlers.record.auto_top_middleware import AutoTopMiddleware

class TestAutoRegistration(unittest.IsolatedAsyncioTestCase):
    async def test_middleware_calls_registration(self):
        # Setup
        middleware = AutoTopMiddleware()
        middleware.service = MagicMock()
        middleware.service.register_user_for_chat_top = AsyncMock()
        
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user.id = 12345
        message.from_user.username = "test_user"
        message.from_user.first_name = "Test"
        message.chat.id = -100123
        message.text = "hello"  # Not a command
        
        # Execute
        await middleware.on_pre_process_message(message, {})
        
        # Verify
        middleware.service.register_user_for_chat_top.assert_called_once_with(
            12345, -100123, "test_user", "Test"
        )
        print("✅ middleware.on_pre_process_message correctly called register_user_for_chat_top")

    async def test_middleware_ignores_commands(self):
        # Setup
        middleware = AutoTopMiddleware()
        middleware.service = MagicMock()
        middleware.service.register_user_for_chat_top = AsyncMock()
        
        # Mock message (command)
        message = MagicMock(spec=types.Message)
        message.from_user.id = 12345
        message.text = "/start"
        
        # Execute
        await middleware.on_pre_process_message(message, {})
        
        # Verify
        middleware.service.register_user_for_chat_top.assert_not_called()
        print("✅ middleware correctly ignored command")

if __name__ == '__main__':
    unittest.main()
