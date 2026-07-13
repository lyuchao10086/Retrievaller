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
        try:
            # yield 让 FastAPI 把这个连接注入到接口函数或 repository 里。
            yield connection
        finally:
            # autocommit=False 时，纯查询也会开启事务；请求结束时回滚空事务，
            # 避免连接池复用旧快照，导致读不到 worker 刚提交的状态变化。
            await connection.rollback()


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
                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR(64) PRIMARY KEY,
                    username VARCHAR(64) NOT NULL,
                    password_hash VARCHAR(512) NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    UNIQUE KEY uq_users_username (username)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            await cursor.execute(
                """
                INSERT IGNORE INTO users (id, username, password_hash, is_active)
                VALUES ('default_user', 'legacy_default_user', NULL, FALSE)
                """
            )
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
                    parsed_bucket VARCHAR(255) NULL,
                    parsed_object_key VARCHAR(1024) NULL,
                    task_id VARCHAR(255) NULL,
                    processing_config_json MEDIUMTEXT NULL,
                    config_version INT NULL,
                    needs_reindex BOOLEAN NOT NULL DEFAULT FALSE,
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
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_base_configs (
                    knowledge_base_id VARCHAR(64) NOT NULL,
                    user_id VARCHAR(128) NOT NULL,
                    processing_config_json MEDIUMTEXT NOT NULL,
                    retrieval_config_json MEDIUMTEXT NOT NULL,
                    generation_config_json MEDIUMTEXT NOT NULL,
                    version INT NOT NULL DEFAULT 1,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    PRIMARY KEY (knowledge_base_id, user_id),
                    CONSTRAINT fk_kb_configs_knowledge_base
                        FOREIGN KEY (knowledge_base_id)
                        REFERENCES knowledge_bases (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    knowledge_base_id VARCHAR(64) NOT NULL,
                    document_id VARCHAR(64) NOT NULL,
                    chunk_index INT NOT NULL,
                    title VARCHAR(512) NULL,
                    content TEXT NOT NULL,
                    chapter VARCHAR(512) NULL,
                    section VARCHAR(512) NULL,
                    subsection VARCHAR(512) NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'created',
                    vector_id VARCHAR(255) NULL,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    UNIQUE KEY uq_chunks_document_index
                        (user_id, knowledge_base_id, document_id, chunk_index),
                    INDEX idx_chunks_user_kb_document
                        (user_id, knowledge_base_id, document_id),
                    INDEX idx_chunks_vector_id (vector_id),
                    CONSTRAINT fk_chunks_knowledge_base
                        FOREIGN KEY (knowledge_base_id)
                        REFERENCES knowledge_bases (id),
                    CONSTRAINT fk_chunks_document
                        FOREIGN KEY (document_id)
                        REFERENCES documents (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_records (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    title VARCHAR(255) NOT NULL DEFAULT '新对话',
                    question TEXT NOT NULL,
                    answer MEDIUMTEXT NOT NULL,
                    knowledge_base_ids MEDIUMTEXT NOT NULL,
                    sources_json MEDIUMTEXT NOT NULL,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    INDEX idx_qa_records_user_created_at
                        (user_id, created_at)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluations (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    qa_record_id VARCHAR(64) NOT NULL,
                    faithfulness_score TINYINT NOT NULL,
                    relevance_score TINYINT NOT NULL,
                    citation_score TINYINT NOT NULL,
                    completeness_score TINYINT NOT NULL,
                    hallucination BOOLEAN NOT NULL,
                    overall_score TINYINT NOT NULL,
                    reason TEXT NOT NULL,
                    raw_response MEDIUMTEXT NOT NULL,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    UNIQUE KEY uq_evaluations_user_qa_record
                        (user_id, qa_record_id),
                    INDEX idx_evaluations_user_created_at
                        (user_id, created_at),
                    CONSTRAINT fk_evaluations_qa_record
                        FOREIGN KEY (qa_record_id)
                        REFERENCES qa_records (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_cases (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    knowledge_base_id VARCHAR(64) NOT NULL,
                    question TEXT NOT NULL,
                    expected_answer MEDIUMTEXT NULL,
                    expected_document_ids_json MEDIUMTEXT NOT NULL,
                    expected_chunk_ids_json MEDIUMTEXT NOT NULL,
                    tags_json MEDIUMTEXT NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    INDEX idx_benchmark_cases_user_kb_enabled
                        (user_id, knowledge_base_id, enabled),
                    CONSTRAINT fk_benchmark_cases_knowledge_base
                        FOREIGN KEY (knowledge_base_id)
                        REFERENCES knowledge_bases (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(128) NOT NULL,
                    knowledge_base_id VARCHAR(64) NOT NULL,
                    task_id VARCHAR(255) NULL,
                    status VARCHAR(32) NOT NULL,
                    config_snapshot_json MEDIUMTEXT NOT NULL,
                    case_snapshot_json MEDIUMTEXT NOT NULL,
                    case_count INT NOT NULL,
                    metrics_json MEDIUMTEXT NULL,
                    error_message TEXT NULL,
                    started_at DATETIME(6) NULL,
                    completed_at DATETIME(6) NULL,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    INDEX idx_benchmark_runs_user_kb_created
                        (user_id, knowledge_base_id, created_at),
                    INDEX idx_benchmark_runs_active (user_id, knowledge_base_id, status),
                    CONSTRAINT fk_benchmark_runs_knowledge_base
                        FOREIGN KEY (knowledge_base_id)
                        REFERENCES knowledge_bases (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_case_results (
                    id VARCHAR(64) PRIMARY KEY,
                    run_id VARCHAR(64) NOT NULL,
                    benchmark_case_id VARCHAR(64) NOT NULL,
                    question TEXT NOT NULL,
                    expected_answer MEDIUMTEXT NULL,
                    expected_document_ids_json MEDIUMTEXT NOT NULL,
                    expected_chunk_ids_json MEDIUMTEXT NOT NULL,
                    tags_json MEDIUMTEXT NOT NULL,
                    answer MEDIUMTEXT NULL,
                    sources_json MEDIUMTEXT NOT NULL,
                    returned_document_ids_json MEDIUMTEXT NOT NULL,
                    returned_chunk_ids_json MEDIUMTEXT NOT NULL,
                    retrieval_document_hit BOOLEAN NULL,
                    retrieval_chunk_hit BOOLEAN NULL,
                    citation_hit BOOLEAN NULL,
                    faithfulness_score TINYINT NULL,
                    relevance_score TINYINT NULL,
                    citation_score TINYINT NULL,
                    completeness_score TINYINT NULL,
                    hallucination BOOLEAN NULL,
                    overall_score TINYINT NULL,
                    evaluation_reason TEXT NULL,
                    duration_ms INT NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    error_message TEXT NULL,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                        ON UPDATE CURRENT_TIMESTAMP(6),
                    INDEX idx_benchmark_results_run_created (run_id, created_at),
                    CONSTRAINT fk_benchmark_results_run
                        FOREIGN KEY (run_id) REFERENCES benchmark_runs (id),
                    CONSTRAINT fk_benchmark_results_case
                        FOREIGN KEY (benchmark_case_id) REFERENCES benchmark_cases (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            await ensure_column_exists(
                cursor,
                table_name="qa_records",
                column_name="title",
                column_definition="VARCHAR(255) NOT NULL DEFAULT '新对话' AFTER user_id",
            )
            await ensure_column_exists(
                cursor,
                table_name="documents",
                column_name="parsed_bucket",
                column_definition="VARCHAR(255) NULL AFTER error_message",
            )
            await ensure_column_exists(
                cursor,
                table_name="documents",
                column_name="parsed_object_key",
                column_definition="VARCHAR(1024) NULL AFTER parsed_bucket",
            )
            await ensure_column_exists(
                cursor,
                table_name="documents",
                column_name="task_id",
                column_definition="VARCHAR(255) NULL AFTER parsed_object_key",
            )
            await ensure_column_exists(
                cursor,
                table_name="documents",
                column_name="processing_config_json",
                column_definition="MEDIUMTEXT NULL AFTER task_id",
            )
            await ensure_column_exists(
                cursor,
                table_name="documents",
                column_name="config_version",
                column_definition="INT NULL AFTER processing_config_json",
            )
            await ensure_column_exists(
                cursor,
                table_name="documents",
                column_name="needs_reindex",
                column_definition="BOOLEAN NOT NULL DEFAULT FALSE AFTER config_version",
            )
            await ensure_column_exists(
                cursor,
                table_name="benchmark_runs",
                column_name="case_snapshot_json",
                column_definition="MEDIUMTEXT NOT NULL AFTER config_snapshot_json",
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
