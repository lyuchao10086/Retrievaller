import asyncio

from minio import Minio

from app.core.config import get_settings
from app.core.database import get_database_pool, init_database
from app.repositories.chunk import MySQLChunkRepository
from app.repositories.document import MySQLDocumentRepository
from app.services.document import (
    DocumentDeletionInProgressError,
    create_document_chunks,
    embed_document_chunks,
    parse_document_to_storage,
)
from app.services.document_storage import MinIODocumentStorage
from app.services.embedding_service import OllamaEmbeddingService
from app.services.knowledge_base import DEFAULT_USER_ID
from app.services.vector_service import MilvusVectorService
from app.tasks.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="app.tasks.document_processing.process_document",
    max_retries=2,
)
def process_document_task(
    self,
    user_id: str,
    kb_id: str,
    document_id: str | dict[str, object] | None = None,
    chunk_settings: dict[str, object] | None = None,
) -> dict[str, str]:
    """后台处理 txt/md 文档；失败后保留 failed 状态并允许手动重试。"""
    user_id, kb_id, document_id, chunk_settings = _normalize_task_args(
        user_id,
        kb_id,
        document_id,
        chunk_settings,
    )
    try:
        return asyncio.run(_process_document(user_id, kb_id, document_id, chunk_settings))
    except DocumentDeletionInProgressError:
        return {
            "user_id": user_id or DEFAULT_USER_ID,
            "kb_id": kb_id,
            "document_id": document_id,
            "status": "deleting",
        }
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=5) from exc
        raise


async def _process_document(
    user_id: str,
    kb_id: str,
    document_id: str,
    chunk_settings: dict[str, object] | None,
) -> dict[str, str]:
    settings = get_settings()
    await init_database()
    pool = await get_database_pool()
    async with pool.acquire() as connection:
        document_repository = MySQLDocumentRepository(connection)
        chunk_repository = MySQLChunkRepository(connection)
        storage = MinIODocumentStorage(
            Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
        )
        embedding_service = OllamaEmbeddingService(
            model_name=settings.embedding_model_name,
            base_url=settings.ollama_base_url,
        )
        vector_service = MilvusVectorService(
            host=settings.milvus_host,
            port=settings.milvus_port,
            collection_name=settings.milvus_collection_document_chunks,
            embedding_dimension=settings.embedding_dimension,
        )

        await parse_document_to_storage(
            document_repository=document_repository,
            storage=storage,
            kb_id=kb_id,
            document_id=document_id,
            user_id=user_id or DEFAULT_USER_ID,
            parsed_bucket_name=settings.minio_bucket_parsed_results,
        )
        await create_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            vector_service=vector_service,
            kb_id=kb_id,
            document_id=document_id,
            user_id=user_id or DEFAULT_USER_ID,
            **_chunk_settings_kwargs(chunk_settings),
        )
        await embed_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            embedding_service=embedding_service,
            vector_service=vector_service,
            kb_id=kb_id,
            document_id=document_id,
            expected_embedding_dimension=settings.embedding_dimension,
            user_id=user_id or DEFAULT_USER_ID,
        )

    return {
        "user_id": user_id or DEFAULT_USER_ID,
        "kb_id": kb_id,
        "document_id": document_id,
        "status": "embedded",
    }


def _chunk_settings_kwargs(
    chunk_settings: dict[str, object] | None,
) -> dict[str, object]:
    if not chunk_settings:
        return {}
    allowed_keys = {
        "separator",
        "chunk_size",
        "chunk_overlap",
        "replace_consecutive_whitespace",
        "remove_urls_and_emails",
    }
    return {
        key: value
        for key, value in chunk_settings.items()
        if key in allowed_keys
    }


def _normalize_task_args(
    user_id: str,
    kb_id: str,
    document_id: str | dict[str, object] | None,
    chunk_settings: dict[str, object] | None,
) -> tuple[str, str, str, dict[str, object] | None]:
    """兼容旧队列中的 (kb_id, document_id, settings) 任务参数。"""
    if isinstance(document_id, str):
        return user_id or DEFAULT_USER_ID, kb_id, document_id, chunk_settings

    legacy_chunk_settings = document_id if isinstance(document_id, dict) else chunk_settings
    return DEFAULT_USER_ID, user_id, kb_id, legacy_chunk_settings
