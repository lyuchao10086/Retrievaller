from datetime import datetime, timezone
from typing import Annotated, Any

import aiomysql
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from minio import Minio

from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.repositories.chunk import ChunkRepository, MySQLChunkRepository
from app.repositories.document import DocumentRepository, MySQLDocumentRepository
from app.repositories.knowledge_base import (
    KnowledgeBaseRepository,
    MySQLKnowledgeBaseRepository,
)
from app.schemas.chunk import ChunkResponse, EmbeddingStatusResponse
from app.schemas.document import DocumentResponse, ParseTaskResponse
from app.services.chunk import (
    embed_document_chunks,
    get_document_embedding_status,
    create_chunks_from_parsed_document,
    list_chunks_by_document,
)
from app.services.document import (
    DocumentNotFoundError,
    KnowledgeBaseNotFoundError,
    ParsedDocumentNotReadyError,
    ParsedResultNotFoundError,
    STATUS_MUST_BE_UPLOADED_MESSAGE,
    UPLOADED_STATUS,
    delete_document,
    get_document_by_id,
    get_parsed_document_content,
    list_documents_by_knowledge_base,
    upload_document_to_knowledge_base,
)
from app.services.document_parse_queue import (
    CeleryParseTaskDispatcher,
    ParseTaskDispatcher,
)
from app.services.document_storage import DocumentStorage, MinIODocumentStorage
from app.services.embedding_service import (
    EmbeddingService,
    OllamaEmbeddingService,
)
from app.services.knowledge_base import DEFAULT_USER_ID
from app.services.vector_service import MilvusVectorService, VectorService


router = APIRouter(
    prefix="/api/knowledge-bases/{kb_id}/documents",
    tags=["documents"],
)


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
    """将当前请求的 MySQL 连接包装成 chunk repository。"""
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


def get_parse_task_dispatcher() -> ParseTaskDispatcher:
    """创建解析任务投递器；测试时可以替换成假的 dispatcher。"""
    return CeleryParseTaskDispatcher()


def get_embedding_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbeddingService:
    """创建 embedding 服务；测试时可替换成假的 embedding 实现。"""
    return OllamaEmbeddingService(
        model_name=settings.embedding_model_name,
        base_url=settings.ollama_base_url,
    )


def get_vector_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VectorService:
    """创建 Milvus 向量写入服务；测试时可替换成内存实现。"""
    return MilvusVectorService(
        host=settings.milvus_host,
        port=settings.milvus_port,
        collection_name=settings.milvus_collection_document_chunks,
        embedding_dimension=settings.embedding_dimension,
    )


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
) -> DocumentResponse:
    """在指定 active 知识库下上传原始文件。

    这一步只保存 MinIO 原始文件和 MySQL 文档记录，不触发解析流水线。
    """
    content = await file.read()
    document = await upload_document_to_knowledge_base(
        knowledge_base_repository=knowledge_base_repository,
        document_repository=document_repository,
        storage=storage,
        kb_id=kb_id,
        file_name=file.filename or "uploaded_file",
        file_type=file.content_type,
        content=content,
        bucket_name=settings.minio_bucket_documents,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return DocumentResponse.model_validate(document)


@router.post(
    "/{document_id}/chunks",
    response_model=list[ChunkResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_document_chunks_api(
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
    """从 parsed JSON 生成当前文档的 chunk 记录。

    当前阶段只保存 MySQL chunk，不做 embedding、Milvus、LangChain 或大模型。
    """
    try:
        chunks = await create_chunks_from_parsed_document(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            kb_id=kb_id,
            document_id=document_id,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    except (ParsedResultNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return [ChunkResponse.model_validate(chunk) for chunk in chunks]


@router.post("/{document_id}/embed", response_model=EmbeddingStatusResponse)
async def embed_document_chunks_api(
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
) -> EmbeddingStatusResponse:
    """给当前文档的 chunks 生成 embedding 并写入 Milvus。"""
    try:
        await embed_document_chunks(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            embedding_service=embedding_service,
            vector_service=vector_service,
            kb_id=kb_id,
            document_id=document_id,
        )
        status_payload = await get_document_embedding_status(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            kb_id=kb_id,
            document_id=document_id,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        ) from exc
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

    return EmbeddingStatusResponse(**status_payload)


@router.get(
    "/{document_id}/embedding-status",
    response_model=EmbeddingStatusResponse,
)
async def get_document_embedding_status_api(
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
    """查询当前文档的 embedding 进度。"""
    try:
        status_payload = await get_document_embedding_status(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            kb_id=kb_id,
            document_id=document_id,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc

    return EmbeddingStatusResponse(**status_payload)


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
async def list_document_chunks_api(
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
    """列出当前文档已生成的 chunks，按 chunk_index 升序返回。"""
    try:
        chunks = await list_chunks_by_document(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            kb_id=kb_id,
            document_id=document_id,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc

    return [ChunkResponse.model_validate(chunk) for chunk in chunks]


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
async def get_document_detail_api(
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
) -> DocumentResponse:
    """查询指定知识库下的单个文档元数据。

    先确认知识库 active，再按 document_id + user_id + kb_id 查询文档，
    不读取 MinIO 文件内容。
    """
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
    return DocumentResponse.model_validate(document)


@router.get("/{document_id}/parsed", response_model=dict[str, Any])
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
) -> dict[str, Any]:
    """预览指定文档的 parsed JSON。

    只读取已经 parsed 的结果，不做 chunk、embedding、Milvus 或大模型调用。
    """
    try:
        return await get_parsed_document_content(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            storage=storage,
            kb_id=kb_id,
            document_id=document_id,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        ) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    except (ParsedDocumentNotReadyError, ParsedResultNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


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
) -> DocumentResponse:
    """软删除指定知识库下的文档元数据。

    这里只更新 documents.status，不删除 MinIO 文件、Milvus 向量或 chunk。
    """
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        DEFAULT_USER_ID,
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    document = await delete_document(document_repository, kb_id, document_id)
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
    parse_task_dispatcher: Annotated[
        ParseTaskDispatcher,
        Depends(get_parse_task_dispatcher),
    ],
) -> ParseTaskResponse:
    """提交异步文档解析任务。

    API 只做沙箱校验和任务投递，不阻塞等待后台解析完成。
    """
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
    if document.status != UPLOADED_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=STATUS_MUST_BE_UPLOADED_MESSAGE,
        )

    task_id = parse_task_dispatcher.submit(kb_id, document_id, DEFAULT_USER_ID)
    updated_document = await document_repository.set_task_id_by_id_and_knowledge_base(
        DEFAULT_USER_ID,
        kb_id,
        document_id,
        task_id,
        datetime.now(timezone.utc).replace(tzinfo=None),
    )
    if updated_document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return ParseTaskResponse(
        message="Parse task submitted",
        document_id=document_id,
        task_id=task_id,
        status=updated_document.status,
    )
