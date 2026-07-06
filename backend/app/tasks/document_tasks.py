import asyncio

import aiomysql
from minio import Minio

from app.core.config import get_settings
from app.core.database import build_mysql_pool_config
from app.repositories.document import MySQLDocumentRepository
from app.services.document_parse_processor import process_document_parse
from app.services.document_storage import MinIODocumentStorage
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.document_tasks.parse_document_task")
def parse_document_task(kb_id: str, document_id: str, user_id: str) -> None:
    """Celery 入口：把同步 worker 进程中的任务转到 async service 执行。"""
    asyncio.run(_parse_document_task(kb_id, document_id, user_id))


async def _parse_document_task(kb_id: str, document_id: str, user_id: str) -> None:
    """后台解析文档。

    当前阶段只支持 Markdown，不做 PDF/Word/Excel/OCR/chunk/向量化。
    """
    settings = get_settings()
    connection = await aiomysql.connect(**build_mysql_pool_config(settings))
    try:
        document_repository = MySQLDocumentRepository(connection)
        minio_client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        storage = MinIODocumentStorage(minio_client)
        await process_document_parse(
            document_repository=document_repository,
            storage=storage,
            kb_id=kb_id,
            document_id=document_id,
            user_id=user_id,
            parsed_bucket=settings.minio_bucket_parsed_results,
        )
    finally:
        connection.close()
