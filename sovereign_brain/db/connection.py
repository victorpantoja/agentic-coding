"""Async PostgreSQL connection management via SQLAlchemy + asyncpg."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from sovereign_brain.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create a SQLAlchemy async engine backed by asyncpg."""
    url = settings.database_url.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    ).replace(
        "postgres://", "postgresql+asyncpg://", 1
    )
    return create_async_engine(url, pool_size=5, pool_pre_ping=True)


@asynccontextmanager
async def get_connection(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    """Yield a single async connection from the engine pool."""
    async with engine.connect() as conn:
        yield conn
