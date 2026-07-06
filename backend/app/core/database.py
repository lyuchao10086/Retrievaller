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
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    knowledge_base_id VARCHAR(64) NOT NULL,
                    file_name VARCHAR(512) NOT NULL,
                    file_type VARCHAR(128) NOT NULL,
                    file_size BIGINT NOT NULL,
                    storage_bucket VARCHAR(255) NOT NULL,
                    storage_object_key VARCHAR(1024) NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'uploaded',
                    error_message TEXT NULL,
                    task_id VARCHAR(255) NULL,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    INDEX idx_doc_user_kb_created_at
                        (user_id, knowledge_base_id, created_at),
                    INDEX idx_doc_knowledge_base_id (knowledge_base_id),
                    CONSTRAINT fk_documents_knowledge_base
                        FOREIGN KEY (knowledge_base_id)
                        REFERENCES knowledge_bases (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            await ensure_column_exists(
                cursor,
                table_name="documents",
                column_name="task_id",
                column_definition="VARCHAR(255) NULL AFTER error_message",
            )
        await connection.commit()


async def ensure_column_exists(
    cursor: aiomysql.Cursor,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    """给自动建表模式补充新增列。

    当前项目还没有 Alembic；已有数据库不会因为 CREATE TABLE IF NOT EXISTS
    自动新增字段，所以这里显式检查并 ALTER。
    """
    await cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table_name, column_name),
    )
    row = await cursor.fetchone()
    column_exists = bool(row and row[0])
    if not column_exists:
        await cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )
