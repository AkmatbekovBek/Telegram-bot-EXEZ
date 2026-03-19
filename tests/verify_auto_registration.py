import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.append(r"c:\RouletteBotTelegram")

try:
    from handlers.record.auto_top_middleware import AutoTopMiddleware
    from aiogram import types
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

async def test_middleware_calls_registration():
    print("Running test_middleware_calls_registration...")
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
    try:
        middleware.service.register_user_for_chat_top.assert_called_once_with(
            12345, -100123, "test_user", "Test"
        )
        print("✅ test_middleware_calls_registration PASSED")
    except AssertionError as e:
        print(f"❌ test_middleware_calls_registration FAILED: {e}")
        sys.exit(1)

async def test_middleware_ignores_commands():
    print("Running test_middleware_ignores_commands...")
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
    try:
        middleware.service.register_user_for_chat_top.assert_not_called()
        print("✅ test_middleware_ignores_commands PASSED")
    except AssertionError as e:
        print(f"❌ test_middleware_ignores_commands FAILED: {e}")
        sys.exit(1)

async def main():
    await test_middleware_calls_registration()
    await test_middleware_ignores_commands()

if __name__ == '__main__':
    asyncio.run(main())
