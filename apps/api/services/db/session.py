from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from contextlib import asynccontextmanager
import asyncpg
from core.config import get_settings

settings = get_settings()

# Engine with explicit connection pool configuration
# pool_size: number of persistent connections maintained
# max_overflow: additional connections beyond pool_size allowed under load
# pool_timeout: seconds to wait for a connection before raising an error
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,     # Verify connections are alive before using
    echo=settings.environment == "development",
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_db_session():
    """Async context manager for SQLAlchemy sessions."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_raw_connection():
    """
    Direct asyncpg connection for operations that need raw SQL
    (e.g., array operations on embeddings that SQLAlchemy handles poorly).
    """
    conn = await asyncpg.connect(
        settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    )
    try:
        yield conn
    finally:
        await conn.close()


# Health check helper
async def check_postgres() -> str:
    try:
        async with get_raw_connection() as conn:
            await conn.fetchval("SELECT 1")
        return "ok"
    except Exception as e:
        return f"error: {str(e)[:100]}"
