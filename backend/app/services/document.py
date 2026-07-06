import inspect
from collections.abc import Awaitable, Callable
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
PARSING_STATUS = "parsing"
PARSED_STATUS = "parsed"
FAILED_STATUS = "failed"
DEFAULT_FILE_TYPE = "application/octet-stream"
STATUS_MUST_BE_UPLOADED_MESSAGE = "Document status must be uploaded before parsing"


class DocumentStatusError(ValueError):
    """文档状态不允许执行当前操作。"""


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
    """软删除当前逻辑用户在指定知识库下的文档记录。

    只把 documents.status 改为 deleted，不删除 MinIO 文件、Milvus 向量或 chunk。
    """
    existing = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if existing is None:
        return None

    deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return await document_repository.soft_delete_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
        deleted_at,
    )


async def parse_document(
    document_repository: DocumentRepository,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
    parse_runner: Callable[[], None | Awaitable[None]] | None = None,
) -> Document | None:
    """模拟文档解析状态流转。

    当前阶段只跑状态机：uploaded -> parsing -> parsed。
    不读取 MinIO 文件内容，不做 OCR、chunk、向量化或大模型调用。
    """
    document = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if document is None:
        return None
    if document.status != UPLOADED_STATUS:
        raise DocumentStatusError(STATUS_MUST_BE_UPLOADED_MESSAGE)

    await _set_document_status(
        document_repository,
        user_id,
        kb_id,
        document_id,
        PARSING_STATUS,
        None,
    )
    try:
        if parse_runner is not None:
            result = parse_runner()
            if inspect.isawaitable(result):
                await result
        return await _set_document_status(
            document_repository,
            user_id,
            kb_id,
            document_id,
            PARSED_STATUS,
            None,
        )
    except Exception as exc:
        return await _set_document_status(
            document_repository,
            user_id,
            kb_id,
            document_id,
            FAILED_STATUS,
            str(exc),
        )


async def _set_document_status(
    document_repository: DocumentRepository,
    user_id: str,
    kb_id: str,
    document_id: str,
    status: str,
    error_message: str | None,
) -> Document | None:
    """写入文档状态并刷新更新时间。"""
    return await document_repository.update_status_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
        status,
        error_message,
        datetime.now(timezone.utc).replace(tzinfo=None),
    )
