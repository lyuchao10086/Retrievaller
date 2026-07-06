from collections.abc import AsyncGenerator

import aiomysql

from app.core.config import Settings, get_settings


_pool: aiomysql.Pool | None = None


def build_mysql_pool_config(settings: Settings) -> dict[str, object]:
    """Build aiomysql connection options from application settings."""
    return {
        "host": settings.mysql_host,
        "port": settings.mysql_port,
        "user": settings.mysql_user,
        "password": settings.mysql_password,
        "db": settings.mysql_database,
        "autocommit": False,
        "charset": "utf8mb4",
    }


async def init_database() -> None:
    """Initialize the shared MySQL pool and make sure required tables exist."""
    global _pool

    if _pool is None:
        _pool = await aiomysql.create_pool(**build_mysql_pool_config(get_settings()))

    await create_tables()


async def close_database() -> None:
    """Close the shared MySQL pool during application shutdown."""
    global _pool

    if _pool is None:
        return

    _pool.close()
    await _pool.wait_closed()
    _pool = None


async def get_database_pool() -> aiomysql.Pool:
    """Return the shared MySQL pool, creating it lazily if needed."""
    if _pool is None:
        await init_database()
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool


async def get_db_connection() -> AsyncGenerator[aiomysql.Connection, None]:
    """FastAPI dependency that yields one pooled MySQL connection per request."""
    pool = await get_database_pool()
    async with pool.acquire() as connection:
        yield connection


async def create_tables() -> None:
    """Create tables needed by the current backend phase.

    This lightweight bootstrap keeps phase 1 simple. When schema changes become
    more complex, this should move to a migration tool such as Alembic.
    """
    pool = await get_database_pool()
    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_bases (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'active',
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    INDEX idx_kb_user_status_created_at
                        (user_id, status, created_at)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
        await connection.commit()
