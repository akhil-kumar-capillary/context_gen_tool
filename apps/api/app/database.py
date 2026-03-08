from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # Connection pool — sized for single-worker Railway deployment (~512 MB).
    # Each idle connection holds ~5-10 MB of PostgreSQL memory.
    pool_size=5,           # Baseline connections kept in the pool
    max_overflow=10,       # Extra connections allowed beyond pool_size under load (max 15)
    pool_recycle=300,      # Recycle connections every 5 minutes to avoid stale connections
    pool_pre_ping=True,    # Test connection health before using it from the pool
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
