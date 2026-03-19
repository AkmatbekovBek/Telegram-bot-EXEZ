from database.engine import engine
from database.models import Base
from database.models import ModerationLog

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
