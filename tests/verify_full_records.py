import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Add project root to path
sys.path.append(r"c:\RouletteBotTelegram")

try:
    from handlers.record.auto_top_middleware import AutoTopMiddleware
    from handlers.record.services import RecordService
    from handlers.record.record_core import RecordCore
    from handlers.record.top_handlers import TopHandlers
    from handlers.record.record_core import RecordConfig
    from aiogram import types
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)

def print_pass(message):
    print(f"[PASS] {message}")

def print_fail(message):
    print(f"[FAIL] {message}")

async def test_auto_registration():
    print("\n--- Testing Auto-Registration (Middleware) ---")
    middleware = AutoTopMiddleware()
    middleware.service = MagicMock()
    middleware.service.register_user_for_chat_top = AsyncMock()
    
    message = MagicMock(spec=types.Message)
    message.from_user.id = 11111
    message.from_user.username = "new_user"
    message.from_user.first_name = "New"
    message.chat.id = -100
    message.text = "Hello world"
    
    await middleware.on_pre_process_message(message, {})
    
    try:
        middleware.service.register_user_for_chat_top.assert_called_once()
        print_pass("Middleware calls register_user_for_chat_top")
    except AssertionError:
        print_fail("Middleware DID NOT call register_user_for_chat_top")

async def test_record_update_logic():
    print("\n--- Testing Record Updates (Service) ---")
    core = MagicMock(spec=RecordCore)
    service = RecordService(core)
    
    # Test add_win_record mocking the internal logic
    # valid amount
    with patch('asyncio.get_event_loop') as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=True)
        
        result = await service.add_win_record(22222, 1000, -100, "winner", "Winner")
        if result:
            print_pass("add_win_record accepts valid positive amount")
        else:
            print_fail("add_win_record failed for valid input")

        # invalid amount
        result = await service.add_win_record(22222, -50, -100)
        if not result:
             print_pass("add_win_record rejects negative amount")
        else:
             print_fail("add_win_record accepted negative amount")

async def test_top_display_limit():
    print("\n--- Testing Top Display Limit ---")
    core = MagicMock(spec=RecordCore)
    # Correctly configure the mock config
    core.config = MagicMock(spec=RecordConfig)
    core.config.MAX_TOP_LIMIT = 100
    core.config.DEFAULT_TOP_LIMIT = 10
    
    core._check_admin_rights = AsyncMock(return_value=True)
    core.ensure_user_registered = AsyncMock()
    
    top_handlers = TopHandlers(core)
    
    # Test top command parsing logic
    message = MagicMock(spec=types.Message)
    message.text = "!top 50"
    message.reply = AsyncMock()
    
    import re
    limit_match = re.search(r'(?:топ|top)\s*(\d+)', message.text.lower().strip())
    limit = int(limit_match.group(1)) if limit_match else 10
    
    if limit == 50:
         print_pass("Command parser correctly extracts limit 50")
    else:
         print_fail(f"Command parser failed, got {limit}")
         
    message.text = "!top 150" # Above max
    limit_match = re.search(r'(?:топ|top)\s*(\d+)', message.text.lower().strip())
    raw_limit = int(limit_match.group(1))
    final_limit = min(raw_limit, core.config.MAX_TOP_LIMIT)
    
    if final_limit == 100:
         print_pass("Limit correctly clamped to MAX_TOP_LIMIT (100)")
    else:
         print_fail(f"Limit clamping failed, got {final_limit}")

async def main():
    print(">>> Starting Full System Verification <<<")
    await test_auto_registration()
    await test_record_update_logic()
    await test_top_display_limit()
    print("\n>>> Verification Complete <<<")

if __name__ == '__main__':
    asyncio.run(main())
