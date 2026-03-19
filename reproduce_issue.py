import sys
import os

print(f"Python executable: {sys.executable}")
print(f"Sys path: {sys.path}")

try:
    import sqlalchemy
    print(f"SQLAlchemy imported: {sqlalchemy.__file__}")
except ImportError as e:
    print(f"SQLAlchemy import failed: {e}")

sys.path.append(r"c:\RouletteBotTelegram")
print("Added project root to sys.path")

try:
    from handlers.record.auto_top_middleware import AutoTopMiddleware
    print("AutoTopMiddleware imported successfully")
except ImportError as e:
    print(f"AutoTopMiddleware import failed: {e}")
    import traceback
    traceback.print_exc()
