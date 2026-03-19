import sys
import os
import asyncio
from datetime import datetime

# Set encoding to utf-8
sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.append(os.getcwd())

from database import get_db
from database.crud import GroupInviteRepository
from database.models import GroupInvite

async def verify_invite_reset():
    chat_id = -100123456789
    inviter_id = 123456789
    invited_users = [1001, 1002, 1003, 1004, 1005]  # 5 users

    db = next(get_db())
    try:
        print(f"1. Setting up test data (5 invites)...")
        # Clean up existing test data
        GroupInviteRepository.reset_invites(db, inviter_id, chat_id)
        
        # Add 5 fake invites
        for uid in invited_users:
            GroupInviteRepository.add_invite(db, inviter_id, uid, chat_id)
        
        count_before = GroupInviteRepository.get_invites_count(db, inviter_id, chat_id)
        print(f"   Invites count before reset: {count_before}")
        
        if count_before != 5:
            print("❌ FAILED: Failed to create 5 test invites")
            return

        print(f"2. Resetting invites for inviter {inviter_id} in chat {chat_id}...")
        deleted_count = GroupInviteRepository.reset_invites(db, inviter_id, chat_id)
        print(f"   Deleted count: {deleted_count}")

        count_after = GroupInviteRepository.get_invites_count(db, inviter_id, chat_id)
        print(f"   Invites count after reset: {count_after}")

        if count_after == 0 and deleted_count == 5:
            print("SUCCESS: Invite counter reset correctly!")
        else:
            print(f"FAILED: Expected 0 invites, got {count_after}")

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(verify_invite_reset())
