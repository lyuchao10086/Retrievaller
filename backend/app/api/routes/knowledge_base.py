from datetime import datetime, timezone
from typing import Annotated

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, status
from minio import Minio

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.repositories.document import DocumentRepository, MySQLDocumentRepository
from app.repositories.knowledge_base import (
    KnowledgeBaseRepository,
    MySQLKnowledgeBaseRepository,
)
from app.repositories.knowledge_base_config import (
    KnowledgeBaseConfigRepository,
    MySQLKnowledgeBaseConfigRepository,
)
from app.schemas.knowledge_base_config import (
    KnowledgeBaseConfigResponse,
    KnowledgeBaseConfigUpdate,
)
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.services.knowledge_base import (
    create_knowledge_base,
    delete_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    update_knowledge_base,
)
from app.services.knowledge_base_config import (
    apply_config_update,
    ConfigurationDependencyError,
    get_or_create_knowledge_base_config,
    indexing_config_changed,
    ModelConfigurationError,
    validate_config_update_dependencies,
)
from app.services.document import (
    delete_document_storage_objects,
    list_documents_by_knowledge_base,
)
from app.services.document_storage import DocumentStorage, MinIODocumentStorage
from app.services.vector_service import MilvusVectorService, VectorService


router = APIRouter(
    prefix="/api/knowledge-bases",
    tags=["knowledge-bases"],
    dependencies=[Depends(get_current_user)],
)


def _config_response(config) -> KnowledgeBaseConfigResponse:
    return KnowledgeBaseConfigResponse(
        knowledge_base_id=config.knowledge_base_id,
        processing=config.processing_dict(),
        retrieval=config.retrieval_dict(),
        generation=config.generation_dict(),
        version=config.version,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


async def get_knowledge_base_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> KnowledgeBaseRepository:
    """将当前请求的 MySQL 连接包装成 repository 实例。"""
    return MySQLKnowledgeBaseRepository(connection)


async def get_document_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> DocumentRepository:
    """删除知识库前需要读取其下文档对象位置，用于清理 MinIO。"""
    return MySQLDocumentRepository(connection)


async def get_knowledge_base_config_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> KnowledgeBaseConfigRepository:
    return MySQLKnowledgeBaseConfigRepository(connection)


def get_document_storage(settings: Annotated[Settings, Depends(get_settings)]) -> DocumentStorage:
    """创建 MinIO 存储适配器，用于知识库删除时清理文件对象。"""
    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return MinIODocumentStorage(client)


def get_vector_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VectorService:
    """创建 Milvus 向量服务；删除知识库时需要同步清理该知识库向量。"""
    return MilvusVectorService(
        host=settings.milvus_host,
        port=settings.milvus_port,
        collection_name=settings.milvus_collection_document_chunks,
        embedding_dimension=settings.embedding_dimension,
    )


@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base_api(
    payload: KnowledgeBaseCreate,
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> KnowledgeBaseResponse:
    knowledge_base = await create_knowledge_base(repository, payload, current_user.id)
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases_api(
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[KnowledgeBaseResponse]:
    knowledge_bases = await list_knowledge_bases(repository, current_user.id)
    return [
        KnowledgeBaseResponse.model_validate(knowledge_base)
        for knowledge_base in knowledge_bases
    ]


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base_api(
    kb_id: str,
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> KnowledgeBaseResponse:
    knowledge_base = await get_knowledge_base(repository, kb_id, current_user.id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get("/{kb_id}/config", response_model=KnowledgeBaseConfigResponse)
async def get_knowledge_base_config_api(
    kb_id: str,
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)],
    config_repository: Annotated[KnowledgeBaseConfigRepository, Depends(get_knowledge_base_config_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> KnowledgeBaseConfigResponse:
    if await get_knowledge_base(knowledge_base_repository, kb_id, current_user.id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    config = await get_or_create_knowledge_base_config(
        config_repository, kb_id, current_user.id, settings
    )
    return _config_response(config)


@router.put("/{kb_id}/config", response_model=KnowledgeBaseConfigResponse)
async def update_knowledge_base_config_api(
    kb_id: str,
    payload: KnowledgeBaseConfigUpdate,
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)],
    config_repository: Annotated[KnowledgeBaseConfigRepository, Depends(get_knowledge_base_config_repository)],
    document_repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> KnowledgeBaseConfigResponse:
    if await get_knowledge_base(knowledge_base_repository, kb_id, current_user.id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    current = await get_or_create_knowledge_base_config(
        config_repository, kb_id, current_user.id, settings
    )
    before = type(current)(
        knowledge_base_id=current.knowledge_base_id,
        user_id=current.user_id,
        processing=type(current.processing)(**current.processing_dict()),
        retrieval=type(current.retrieval)(**current.retrieval_dict()),
        generation=type(current.generation)(**current.generation_dict()),
        version=current.version,
        created_at=current.created_at,
        updated_at=current.updated_at,
    )
    updated = apply_config_update(current, payload)
    if updated.processing.chunk_overlap >= updated.processing.chunk_size:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="chunk_overlap must be less than chunk_size")
    try:
        await validate_config_update_dependencies(payload, updated, settings)
    except ModelConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ConfigurationDependencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    changed_indexing = indexing_config_changed(before, updated)
    updated.version += 1
    updated.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    updated = await config_repository.update(updated)
    if changed_indexing:
        await document_repository.mark_needs_reindex_by_knowledge_base(
            current_user.id, kb_id, updated.updated_at
        )
    return _config_response(updated)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base_api(
    kb_id: str,
    payload: KnowledgeBaseUpdate,
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> KnowledgeBaseResponse:
    knowledge_base = await update_knowledge_base(repository, kb_id, payload, current_user.id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.delete("/{kb_id}", response_model=KnowledgeBaseResponse)
async def delete_knowledge_base_api(
    kb_id: str,
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    vector_service: Annotated[
        VectorService,
        Depends(get_vector_service),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> KnowledgeBaseResponse:
    """硬删除当前用户可见的 active 知识库，查不到时返回 404。"""
    knowledge_base = await get_knowledge_base(repository, kb_id, current_user.id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    documents = await list_documents_by_knowledge_base(document_repository, kb_id, current_user.id)
    for document in documents:
        await delete_document_storage_objects(storage, document)
    vector_service.delete_chunk_embeddings_by_knowledge_base(
        current_user.id,
        kb_id,
    )
    knowledge_base = await delete_knowledge_base(repository, kb_id, current_user.id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return KnowledgeBaseResponse.model_validate(knowledge_base)
