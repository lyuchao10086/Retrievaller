from collections.abc import AsyncGenerator

import aiomysql

from app.core.config import Settings, get_settings


_pool: aiomysql.Pool | None = None


def build_mysql_pool_config(settings: Settings) -> dict[str, object]:
    """把config中的配置转成 aiomysql 能识别的连接参数。"""
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
    """初始化共享 MySQL 连接池，并确保当前阶段需要的表已存在。"""
    global _pool

    if _pool is None:
        _pool = await aiomysql.create_pool(**build_mysql_pool_config(get_settings()))

    await create_tables()


async def close_database() -> None:
    """应用关闭时释放共享 MySQL 连接池。"""
    global _pool

    if _pool is None:
        return

    _pool.close()
    await _pool.wait_closed()
    _pool = None


async def get_database_pool() -> aiomysql.Pool:
    """获取共享 MySQL 连接池，尚未初始化时会自动创建。"""
    if _pool is None:
        await init_database()
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool


async def get_db_connection() -> AsyncGenerator[aiomysql.Connection, None]:
    """FastAPI 依赖：为每个请求提供一个来自连接池的 MySQL 连接。"""
    pool = await get_database_pool()
    async with pool.acquire() as connection:
        # yield 让 FastAPI 把这个连接注入到接口函数或 repository 里
        yield connection


async def create_tables() -> None:
    """创建当前后端阶段需要的数据表。

    这里先用轻量级启动建表保持第 1 步简单；当表结构演进复杂后，
    应该迁移到 Alembic 这类数据库迁移工具。
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
