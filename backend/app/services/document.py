from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models.document import Document
from app.repositories.document import DocumentRepository
from app.repositories.knowledge_base import KnowledgeBaseRepository
from app.services.document_storage import DocumentStorage
from app.services.knowledge_base import DEFAULT_USER_ID


DEFAULT_DOCUMENT_BUCKET = "rag-documents"
UPLOADED_STATUS = "uploaded"
DEFAULT_FILE_TYPE = "application/octet-stream"


class KnowledgeBaseNotFoundError(LookupError):
    """当前用户下找不到 active 知识库。"""


class DocumentNotFoundError(LookupError):
    """当前知识库沙箱下找不到可见文档。"""


async def upload_document_to_knowledge_base(
    knowledge_base_repository: KnowledgeBaseRepository,
    document_repository: DocumentRepository,
    storage: DocumentStorage,
    kb_id: str,
    file_name: str,
    file_type: str | None,
    content: bytes,
    user_id: str = DEFAULT_USER_ID,
    bucket_name: str = DEFAULT_DOCUMENT_BUCKET,
) -> Document | None:
    """上传原始文档，并在指定知识库沙箱内保存文档记录。

    这里只保存原始文件和元数据，不做 OCR、解析、切分、向量入库或大模型调用。
    """
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        user_id,
    )
    if knowledge_base is None:
        return None

    document_id = f"doc_{uuid4().hex}"
    safe_file_name = Path(file_name).name or "uploaded_file"
    normalized_file_type = file_type or DEFAULT_FILE_TYPE
    object_key = (
        f"users/{user_id}/knowledge_bases/{kb_id}/raw/"
        f"{document_id}/{safe_file_name}"
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    await storage.ensure_bucket(bucket_name)
    await storage.put_object(
        bucket_name,
        object_key,
        content,
        normalized_file_type,
    )

    document = Document(
        id=document_id,
        user_id=user_id,
        knowledge_base_id=kb_id,
        file_name=safe_file_name,
        file_type=normalized_file_type,
        file_size=len(content),
        storage_bucket=bucket_name,
        storage_object_key=object_key,
        status=UPLOADED_STATUS,
        error_message=None,
        parsed_bucket=None,
        parsed_object_key=None,
        # 异步解析任务提交前没有 task_id，提交后会写入 Celery 返回的任务 ID。
        task_id=None,
        created_at=now,
        updated_at=now,
    )
    return await document_repository.insert(document)


async def list_documents_by_knowledge_base(
    document_repository: DocumentRepository,
    kb_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> list[Document]:
    """列出当前逻辑用户在指定知识库下的文档记录。"""
    return await document_repository.list_by_knowledge_base(user_id, kb_id)


async def get_document_by_id(
    document_repository: DocumentRepository,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> Document | None:
    """查询当前逻辑用户在指定知识库下的单个文档元数据。

    这里只返回 MySQL 元数据，不读取 MinIO 原始文件内容。
    """
    return await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )


async def delete_document(
    document_repository: DocumentRepository,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> Document | None:
    """硬删除当前逻辑用户在指定知识库下的文档记录。"""
    existing = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if existing is None:
        return None

    return await document_repository.delete_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )


async def delete_document_storage_objects(
    storage: DocumentStorage,
    document: Document,
) -> None:
    """物理删除文档在对象存储中的原始文件和解析结果。"""
    await storage.delete_object(
        document.storage_bucket,
        document.storage_object_key,
    )
    if document.parsed_bucket and document.parsed_object_key:
        await storage.delete_object(
            document.parsed_bucket,
            document.parsed_object_key,
        )
