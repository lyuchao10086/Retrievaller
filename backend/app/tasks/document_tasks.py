import asyncio
from datetime import datetime, timezone

import aiomysql

from app.core.config import get_settings
from app.core.database import build_mysql_pool_config
from app.repositories.document import MySQLDocumentRepository
from app.services.document import DocumentStatusError, FAILED_STATUS, parse_document
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.document_tasks.parse_document_task")
def parse_document_task(kb_id: str, document_id: str, user_id: str) -> None:
    """Celery 入口：把同步 worker 进程中的任务转到 async service 执行。"""
    asyncio.run(_parse_document_task(kb_id, document_id, user_id))


async def _parse_document_task(kb_id: str, document_id: str, user_id: str) -> None:
    """后台模拟解析：uploaded -> parsing -> parsed。

    当前阶段仍然不读取 MinIO、不做 OCR、不切 chunk、不写 Milvus。
    """
    connection = await aiomysql.connect(**build_mysql_pool_config(get_settings()))
    try:
        document_repository = MySQLDocumentRepository(connection)

        async def simulate_parse() -> None:
            # 模拟后续真实解析耗时，方便接口立即返回后观察状态变化。
            await asyncio.sleep(2)

        try:
            await parse_document(
                document_repository,
                kb_id,
                document_id,
                user_id=user_id,
                parse_runner=simulate_parse,
            )
        except DocumentStatusError:
            # 任务真正执行时，如果文档已不是 uploaded，说明状态已变化；
            # 这里直接结束，避免 worker 把合法的现有状态改坏。
            return
        except Exception as exc:
            # 兜底处理未预期异常，便于前端和后续任务系统看到失败原因。
            await document_repository.update_status_by_id_and_knowledge_base(
                user_id,
                kb_id,
                document_id,
                FAILED_STATUS,
                str(exc),
                datetime.now(timezone.utc).replace(tzinfo=None),
            )
    finally:
        connection.close()
