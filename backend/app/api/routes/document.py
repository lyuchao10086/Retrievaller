from datetime import datetime, timezone
import json
import logging
from typing import Annotated, Protocol

import aiomysql
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from minio import Minio
from pydantic import BaseModel, ValidationError

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.core.logging import bind_log_context
from app.repositories.chunk import ChunkRepository, MySQLChunkRepository
from app.repositories.document import DocumentRepository, MySQLDocumentRepository
from app.repositories.knowledge_base import (
    KnowledgeBaseRepository,
    MySQLKnowledgeBaseRepository,
)
from app.repositories.knowledge_base_config import KnowledgeBaseConfigRepository
from app.api.routes.knowledge_base import get_knowledge_base_config_repository
from app.schemas.document import (
    ChunkSettingsRequest,
    ChunkResponse,
    DocumentResponse,
    EmbeddingStatusResponse,
    ParsedDocumentResponse,
    ParseTaskResponse,
    ProcessingStatusResponse,
)
from app.services.document import (
    DELETING_STATUS,
    FAILED_STATUS,
    DocumentNotFoundError,
    UnsupportedDocumentTypeError,
    create_document_chunks,
    delete_document_with_cleanup,
    delete_document_storage_objects,
    embed_document_chunks,
    get_document_by_id,
    get_document_embedding_status,
    get_document_processing_status,
    get_parsed_document_payload,
    is_supported_text_document,
    list_document_chunks,
    list_documents_by_knowledge_base,
    parse_document_to_storage,
    rename_document,
    upload_document_to_knowledge_base,
)
from app.services.document_storage import DocumentStorage, MinIODocumentStorage
from app.services.embedding_service import EmbeddingService, OllamaEmbeddingService
from app.services.vector_service import MilvusVectorService, VectorService
from app.services.knowledge_base_config import get_or_create_knowledge_base_config
from app.tasks.document_processing import process_document_task


router = APIRouter(
    prefix="/api/knowledge-bases/{kb_id}/documents",
    tags=["documents"],
    dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)


class ProcessingQueue(Protocol):
    """Celery task 的最小接口；测试中可替换成内存 fake。"""

    def delay(
        self,
        user_id: str,
        kb_id: str,
        document_id: str,
        chunk_settings: dict[str, object] | None = None,
    ):
        raise NotImplementedError


async def get_knowledge_base_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> KnowledgeBaseRepository:
    """文档接口需要先校验知识库是否属于当前逻辑用户。"""
    return MySQLKnowledgeBaseRepository(connection)


async def get_document_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> DocumentRepository:
    """将当前请求的 MySQL 连接包装成文档 repository。"""
    return MySQLDocumentRepository(connection)


async def get_chunk_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> ChunkRepository:
    """文档处理接口需要写入、预览和回写 chunks。"""
    return MySQLChunkRepository(connection)


def get_document_storage(settings: Annotated[Settings, Depends(get_settings)]) -> DocumentStorage:
    """创建 MinIO 存储适配器；测试时可以替换成内存实现。"""
    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return MinIODocumentStorage(client)


def get_embedding_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbeddingService:
    """文档 embedding 必须与 RAG query embedding 使用同一模型。"""
    return OllamaEmbeddingService(
        model_name=settings.embedding_model_name,
        base_url=settings.ollama_base_url,
    )


def get_vector_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VectorService:
    """创建 Milvus 向量清理服务。"""
    return MilvusVectorService(
        host=settings.milvus_host,
        port=settings.milvus_port,
        collection_name=settings.milvus_collection_document_chunks,
        embedding_dimension=settings.embedding_dimension,
    )


def get_processing_queue() -> ProcessingQueue:
    """返回文档处理 Celery task；上传接口只负责入队。"""
    return process_document_task


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_api(
    kb_id: str,
    file: Annotated[UploadFile, File()],
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    chunk_settings: Annotated[str | None, Form()] = None,
) -> DocumentResponse:
    """上传原始文件；处理由 /process 接口显式提交后台任务。"""
    _parse_chunk_settings_form(chunk_settings)
    content = await file.read()
    file_name = file.filename or "uploaded_file"
    file_type = file.content_type
    document = await upload_document_to_knowledge_base(
        knowledge_base_repository=knowledge_base_repository,
        document_repository=document_repository,
        storage=storage,
        kb_id=kb_id,
        file_name=file_name,
        file_type=file_type,
        content=content,
        user_id=current_user.id,
        bucket_name=settings.minio_bucket_documents,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents_api(
    kb_id: str,
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[DocumentResponse]:
    """列出指定知识库沙箱下的文档记录。"""
    documents = await list_documents_by_knowledge_base(document_repository, kb_id, current_user.id)
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_api(
    kb_id: str,
    document_id: str,
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DocumentResponse:
    """查询指定知识库下的单个文档元数据。"""
    document = await get_document_by_id(document_repository, kb_id, document_id, current_user.id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return DocumentResponse.model_validate(document)


@router.post("/{document_id}/parse", response_model=ParseTaskResponse)
async def parse_document_api(
    kb_id: str,
    document_id: str,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ParseTaskResponse:
    """同步解析 txt/markdown 文档，并保存解析 JSON。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    try:
        await parse_document_to_storage(
            document_repository=document_repository,
            storage=storage,
            kb_id=kb_id,
            document_id=document_id,
            user_id=current_user.id,
            parsed_bucket_name=settings.minio_bucket_parsed_results,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    except UnsupportedDocumentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ParseTaskResponse(
        message="Document parsed synchronously",
        document_id=document_id,
        task_id=f"sync_{document_id}",
        status="parsed",
    )


@router.post("/{document_id}/process", response_model=ParseTaskResponse)
async def process_document_api(
    kb_id: str,
    document_id: str,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    config_repository: Annotated[
        KnowledgeBaseConfigRepository,
        Depends(get_knowledge_base_config_repository),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    processing_queue: Annotated[ProcessingQueue, Depends(get_processing_queue)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    body: Annotated[ChunkSettingsRequest | None, Body()] = None,
) -> ParseTaskResponse:
    """把支持的文本类文档重新提交到 Celery 处理队列。"""
    bind_log_context(knowledge_base_id=kb_id, document_id=document_id)
    await _ensure_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    document = await get_document_by_id(document_repository, kb_id, document_id, current_user.id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    if not is_supported_text_document(document.file_name, document.file_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only txt, md and markdown documents are supported",
        )
    if document.status == DELETING_STATUS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is deleting",
        )
    if document.status in {"parsing", "chunking", "embedding"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is already processing",
        )

    config = await get_or_create_knowledge_base_config(
        config_repository, kb_id, current_user.id, settings
    )
    processing_snapshot = config.processing_dict()
    if body is not None:
        processing_snapshot.update(body.model_dump(exclude_none=True))
    if processing_snapshot["chunk_overlap"] >= processing_snapshot["chunk_size"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="chunk_overlap must be less than chunk_size",
        )
    saved_snapshot = await document_repository.set_processing_config_by_id_and_knowledge_base(
        current_user.id,
        kb_id,
        document_id,
        json.dumps(processing_snapshot, ensure_ascii=False),
        config.version,
        _utc_now(),
    )
    if saved_snapshot is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document is not available for processing")
    queued_status_document = await document_repository.update_status_by_id_and_knowledge_base(
        current_user.id,
        kb_id,
        document_id,
        "parsing",
        None,
        _utc_now(),
    )
    if queued_status_document is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not available for processing",
        )

    chunk_settings = processing_snapshot
    try:
        task = processing_queue.delay(current_user.id, kb_id, document_id, chunk_settings)
    except Exception as exc:
        logger.exception(
            "document_processing_queue_unavailable",
            extra={"error_code": "celery_queue_unavailable"},
        )
        await document_repository.update_status_by_id_and_knowledge_base(
            current_user.id,
            kb_id,
            document_id,
            FAILED_STATUS,
            str(exc),
            _utc_now(),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document processing queue is unavailable",
        ) from exc
    queued_document = await document_repository.set_task_id_by_id_and_knowledge_base(
        current_user.id,
        kb_id,
        document_id,
        task.id,
        _utc_now(),
    )
    bind_log_context(task_id=task.id)
    logger.info("document_processing_queued")
    return ParseTaskResponse(
        message="Document processing queued",
        document_id=document_id,
        task_id=task.id,
        status=(queued_document or queued_status_document or document).status,
    )


@router.get("/{document_id}/parsed", response_model=ParsedDocumentResponse)
async def get_parsed_document_api(
    kb_id: str,
    document_id: str,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ParsedDocumentResponse:
    """读取指定文档的解析结果。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    try:
        payload = await get_parsed_document_payload(
            document_repository,
            storage,
            kb_id,
            document_id,
            current_user.id,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed document not found",
        ) from exc
    return ParsedDocumentResponse.model_validate(payload)


@router.post("/{document_id}/chunks", response_model=list[ChunkResponse])
async def create_chunks_api(
    kb_id: str,
    document_id: str,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    chunk_repository: Annotated[
        ChunkRepository,
        Depends(get_chunk_repository),
    ],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
    vector_service: Annotated[
        VectorService,
        Depends(get_vector_service),
    ],
    config_repository: Annotated[
        KnowledgeBaseConfigRepository,
        Depends(get_knowledge_base_config_repository),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[ChunkResponse]:
    """基于原始文本或解析结果同步生成 chunks，默认 500 字符、50 overlap。"""
    bind_log_context(knowledge_base_id=kb_id, document_id=document_id)
    await _ensure_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    config = await get_or_create_knowledge_base_config(
        config_repository, kb_id, current_user.id, settings
    )
    try:
        chunks = await create_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            vector_service=vector_service,
            kb_id=kb_id,
            document_id=document_id,
            user_id=current_user.id,
            **_processing_chunk_kwargs(config.processing_dict()),
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed document not found",
        ) from exc
    except UnsupportedDocumentTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception(
            "document_chunking_failed",
            extra={"error_code": "document_chunking_failed"},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Document chunking failed",
        ) from exc
    return [ChunkResponse.model_validate(chunk) for chunk in chunks]


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
async def list_chunks_api(
    kb_id: str,
    document_id: str,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    chunk_repository: Annotated[
        ChunkRepository,
        Depends(get_chunk_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[ChunkResponse]:
    """列出指定文档的 chunks。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    try:
        chunks = await list_document_chunks(
            document_repository,
            chunk_repository,
            kb_id,
            document_id,
            current_user.id,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    return [ChunkResponse.model_validate(chunk) for chunk in chunks]


@router.post("/{document_id}/embed", response_model=EmbeddingStatusResponse)
async def embed_document_api(
    kb_id: str,
    document_id: str,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    chunk_repository: Annotated[
        ChunkRepository,
        Depends(get_chunk_repository),
    ],
    embedding_service: Annotated[
        EmbeddingService,
        Depends(get_embedding_service),
    ],
    vector_service: Annotated[
        VectorService,
        Depends(get_vector_service),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    config_repository: Annotated[
        KnowledgeBaseConfigRepository,
        Depends(get_knowledge_base_config_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> EmbeddingStatusResponse:
    """同步生成 chunks embedding 并写入 Milvus。"""
    bind_log_context(knowledge_base_id=kb_id, document_id=document_id)
    await _ensure_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    config = await get_or_create_knowledge_base_config(
        config_repository, kb_id, current_user.id, settings
    )
    try:
        payload = await embed_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            embedding_service=embedding_service,
            vector_service=vector_service,
            kb_id=kb_id,
            document_id=document_id,
            expected_embedding_dimension=settings.embedding_dimension,
            embedding_model_name=config.processing.embedding_model_name,
            user_id=current_user.id,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception(
            "document_embedding_failed",
            extra={"error_code": "document_embedding_failed"},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document embedding failed",
        ) from exc
    return EmbeddingStatusResponse.model_validate(payload)


@router.get("/{document_id}/embedding-status", response_model=EmbeddingStatusResponse)
async def get_embedding_status_api(
    kb_id: str,
    document_id: str,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    chunk_repository: Annotated[
        ChunkRepository,
        Depends(get_chunk_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> EmbeddingStatusResponse:
    """返回文档 chunks 的 embedding 进度。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    try:
        payload = await get_document_embedding_status(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            kb_id=kb_id,
            document_id=document_id,
            user_id=current_user.id,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    return EmbeddingStatusResponse.model_validate(payload)


@router.get("/{document_id}/processing-status", response_model=ProcessingStatusResponse)
async def get_processing_status_api(
    kb_id: str,
    document_id: str,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    chunk_repository: Annotated[
        ChunkRepository,
        Depends(get_chunk_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ProcessingStatusResponse:
    """返回文档后台处理进度，包含 Celery task_id、错误和 chunk 统计。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    try:
        payload = await get_document_processing_status(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            kb_id=kb_id,
            document_id=document_id,
            user_id=current_user.id,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    return ProcessingStatusResponse.model_validate(payload)


@router.delete("/{document_id}", response_model=DocumentResponse)
async def delete_document_api(
    kb_id: str,
    document_id: str,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    chunk_repository: Annotated[
        ChunkRepository,
        Depends(get_chunk_repository),
    ],
    vector_service: Annotated[
        VectorService,
        Depends(get_vector_service),
    ],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DocumentResponse:
    """按可重试顺序清理文档索引和对象，并保留 deleted 生命周期终态。"""
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        current_user.id,
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    document = await get_document_by_id(document_repository, kb_id, document_id, current_user.id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    try:
        document = await delete_document_with_cleanup(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            vector_service=vector_service,
            kb_id=kb_id,
            document_id=document_id,
            user_id=current_user.id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Document deletion is pending retry",
        ) from exc
    return DocumentResponse.model_validate(document)


async def _ensure_knowledge_base(
    knowledge_base_repository: KnowledgeBaseRepository,
    kb_id: str,
    user_id: str,
) -> None:
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        user_id,
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _processing_chunk_kwargs(processing_config: dict[str, object]) -> dict[str, object]:
    supported_keys = {
        "separator",
        "chunk_size",
        "chunk_overlap",
        "replace_consecutive_whitespace",
        "remove_urls_and_emails",
    }
    return {
        key: value
        for key, value in processing_config.items()
        if key in supported_keys
    }


def _parse_chunk_settings_form(
    chunk_settings: str | None,
) -> dict[str, object] | None:
    if not chunk_settings:
        return None
    try:
        payload = json.loads(chunk_settings)
        return ChunkSettingsRequest.model_validate(payload).model_dump()
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid chunk_settings",
        ) from exc


class RenameDocumentRequest(BaseModel):
    """重命名文档的请求体。"""

    file_name: str


@router.patch("/{document_id}", response_model=DocumentResponse)
async def rename_document_api(
    kb_id: str,
    document_id: str,
    body: RenameDocumentRequest,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> DocumentResponse:
    """重命名指定知识库下的文档文件名。"""
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        current_user.id,
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    document = await rename_document(
        document_repository,
        kb_id,
        document_id,
        body.file_name,
        current_user.id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return DocumentResponse.model_validate(document)
