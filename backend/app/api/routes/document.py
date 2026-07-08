from typing import Annotated

import aiomysql
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from minio import Minio

from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.repositories.document import DocumentRepository, MySQLDocumentRepository
from app.repositories.knowledge_base import (
    KnowledgeBaseRepository,
    MySQLKnowledgeBaseRepository,
)
from app.schemas.document import DocumentResponse
from app.services.document import (
    delete_document,
    delete_document_storage_objects,
    get_document_by_id,
    list_documents_by_knowledge_base,
    upload_document_to_knowledge_base,
)
from app.services.document_storage import DocumentStorage, MinIODocumentStorage
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


def get_document_storage(settings: Annotated[Settings, Depends(get_settings)]) -> DocumentStorage:
    """创建 MinIO 存储适配器；测试时可以替换成内存实现。"""
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
    """创建 Milvus 向量清理服务。"""
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
    """在指定 active 知识库下上传原始文件，只保存原始文件和文档记录。"""
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
