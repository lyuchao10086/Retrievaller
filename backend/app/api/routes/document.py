from datetime import datetime, timezone
import json
from typing import Annotated, Protocol

import aiomysql
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from minio import Minio
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.repositories.chunk import ChunkRepository, MySQLChunkRepository
from app.repositories.document import DocumentRepository, MySQLDocumentRepository
from app.repositories.knowledge_base import (
    KnowledgeBaseRepository,
    MySQLKnowledgeBaseRepository,
)
from app.schemas.document import (
    ChunkSettingsRequest,
    ChunkResponse,
    DocumentResponse,
    EmbeddingStatusResponse,
    ParsedDocumentResponse,
    ParseTaskResponse,
)
from app.services.document import (
    DocumentNotFoundError,
    UnsupportedDocumentTypeError,
    create_document_chunks,
    delete_document,
    delete_document_storage_objects,
    embed_document_chunks,
    get_document_by_id,
    get_document_embedding_status,
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
from app.services.knowledge_base import DEFAULT_USER_ID
from app.services.vector_service import MilvusVectorService, VectorService
from app.tasks.document_processing import process_document_task


router = APIRouter(
    prefix="/api/knowledge-bases/{kb_id}/documents",
    tags=["documents"],
)


class ProcessingQueue(Protocol):
    """Celery task 的最小接口；测试中可替换成内存 fake。"""

    def delay(
        self,
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
    processing_queue: Annotated[ProcessingQueue, Depends(get_processing_queue)],
    settings: Annotated[Settings, Depends(get_settings)],
    chunk_settings: Annotated[str | None, Form()] = None,
) -> DocumentResponse:
    """上传原始文件；txt/markdown 入队后台处理，响应不等待 embedding。"""
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
        bucket_name=settings.minio_bucket_documents,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    if not is_supported_text_document(file_name, file_type):
        return DocumentResponse.model_validate(document)

    chunk_settings_payload = _parse_chunk_settings_form(chunk_settings)
    task = processing_queue.delay(kb_id, document.id, chunk_settings_payload)
    queued_document = (
        await document_repository.set_task_id_by_id_and_knowledge_base(
            DEFAULT_USER_ID,
            kb_id,
            document.id,
            task.id,
            _utc_now(),
        )
    )
    return DocumentResponse.model_validate(queued_document or document)


@router.get("", response_model=list[DocumentResponse])
async def list_documents_api(
    kb_id: str,
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
) -> list[DocumentResponse]:
    """列出指定知识库沙箱下的文档记录。"""
    documents = await list_documents_by_knowledge_base(document_repository, kb_id)
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document_api(
    kb_id: str,
    document_id: str,
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
) -> DocumentResponse:
    """查询指定知识库下的单个文档元数据。"""
    document = await get_document_by_id(document_repository, kb_id, document_id)
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
) -> ParseTaskResponse:
    """同步解析 txt/markdown 文档，并保存解析 JSON。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id)
    try:
        await parse_document_to_storage(
            document_repository=document_repository,
            storage=storage,
            kb_id=kb_id,
            document_id=document_id,
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
    processing_queue: Annotated[ProcessingQueue, Depends(get_processing_queue)],
    body: Annotated[ChunkSettingsRequest | None, Body()] = None,
) -> ParseTaskResponse:
    """把支持的文本类文档重新提交到 Celery 处理队列。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id)
    document = await get_document_by_id(document_repository, kb_id, document_id)
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

    await document_repository.update_status_by_id_and_knowledge_base(
        DEFAULT_USER_ID,
        kb_id,
        document_id,
        "uploaded",
        None,
        _utc_now(),
    )
    chunk_settings = body.model_dump() if body is not None else None
    task = processing_queue.delay(kb_id, document_id, chunk_settings)
    queued_document = await document_repository.set_task_id_by_id_and_knowledge_base(
        DEFAULT_USER_ID,
        kb_id,
        document_id,
        task.id,
        _utc_now(),
    )
    return ParseTaskResponse(
        message="Document processing queued",
        document_id=document_id,
        task_id=task.id,
        status=(queued_document or document).status,
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
) -> ParsedDocumentResponse:
    """读取指定文档的解析结果。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id)
    try:
        payload = await get_parsed_document_payload(
            document_repository,
            storage,
            kb_id,
            document_id,
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
) -> list[ChunkResponse]:
    """基于解析结果同步生成 chunks，默认 500 字符、50 overlap。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id)
    try:
        chunks = await create_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            kb_id=kb_id,
            document_id=document_id,
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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
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
) -> list[ChunkResponse]:
    """列出指定文档的 chunks。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id)
    try:
        chunks = await list_document_chunks(
            document_repository,
            chunk_repository,
            kb_id,
            document_id,
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
) -> EmbeddingStatusResponse:
    """同步生成 chunks embedding 并写入 Milvus。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id)
    try:
        payload = await embed_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            embedding_service=embedding_service,
            vector_service=vector_service,
            kb_id=kb_id,
            document_id=document_id,
            expected_embedding_dimension=settings.embedding_dimension,
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
) -> EmbeddingStatusResponse:
    """返回文档 chunks 的 embedding 进度。"""
    await _ensure_knowledge_base(knowledge_base_repository, kb_id)
    try:
        payload = await get_document_embedding_status(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            kb_id=kb_id,
            document_id=document_id,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    return EmbeddingStatusResponse.model_validate(payload)


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
    vector_service: Annotated[
        VectorService,
        Depends(get_vector_service),
    ],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
) -> DocumentResponse:
    """硬删除指定知识库下的文档元数据、对象存储文件和关联向量。"""
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        DEFAULT_USER_ID,
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    document = await get_document_by_id(document_repository, kb_id, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await delete_document_storage_objects(storage, document)
    vector_service.delete_chunk_embeddings_by_document(
        DEFAULT_USER_ID,
        kb_id,
        document_id,
    )
    document = await delete_document(document_repository, kb_id, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return DocumentResponse.model_validate(document)


async def _ensure_knowledge_base(
    knowledge_base_repository: KnowledgeBaseRepository,
    kb_id: str,
) -> None:
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        DEFAULT_USER_ID,
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
) -> DocumentResponse:
    """重命名指定知识库下的文档文件名。"""
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        DEFAULT_USER_ID,
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
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return DocumentResponse.model_validate(document)
