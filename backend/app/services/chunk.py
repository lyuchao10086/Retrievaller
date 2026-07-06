import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.chunk import Chunk
from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.repositories.knowledge_base import KnowledgeBaseRepository
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService
from app.services.document import (
    DocumentNotFoundError,
    KnowledgeBaseNotFoundError,
    PARSED_RESULT_NOT_FOUND_MESSAGE,
    PARSED_STATUS,
    ParsedResultNotFoundError,
)
from app.services.document_storage import DocumentStorage
from app.services.knowledge_base import DEFAULT_USER_ID


CHUNKED_STATUS = "chunked"
EMBEDDED_STATUS = "embedded"
CHUNK_CREATED_STATUS = "created"
DOCUMENT_MUST_BE_PARSED_MESSAGE = "Document must be parsed before chunking"
DOCUMENT_MUST_BE_CHUNKED_MESSAGE = "Document must be chunked before embedding"
CHUNKS_ALREADY_EXIST_MESSAGE = "Chunks already exist for this document"
NO_CHUNKS_AVAILABLE_FOR_EMBEDDING_MESSAGE = "No chunks available for embedding"


async def create_chunks_from_parsed_document(
    knowledge_base_repository: KnowledgeBaseRepository,
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    storage: DocumentStorage,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> list[Chunk]:
    """从 parsed JSON 中生成 chunk 记录。

    当前版本采用简单规则：一个非空 section.content 生成一个 chunk。
    """
    await _ensure_active_knowledge_base(knowledge_base_repository, kb_id, user_id)
    document = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if document is None:
        raise DocumentNotFoundError("Document not found")

    if await chunk_repository.exists_by_document(user_id, kb_id, document_id):
        raise ValueError(CHUNKS_ALREADY_EXIST_MESSAGE)
    if document.status != PARSED_STATUS:
        raise ValueError(DOCUMENT_MUST_BE_PARSED_MESSAGE)
    if not document.parsed_bucket or not document.parsed_object_key:
        raise ParsedResultNotFoundError(PARSED_RESULT_NOT_FOUND_MESSAGE)

    parsed_bytes = await storage.get_object(
        document.parsed_bucket,
        document.parsed_object_key,
    )
    parsed_json = json.loads(parsed_bytes.decode("utf-8"))
    chunks = _build_chunks_from_sections(
        parsed_json.get("sections", []),
        user_id=user_id,
        kb_id=kb_id,
        document_id=document_id,
    )
    saved_chunks = await chunk_repository.insert_many(chunks)
    await document_repository.update_status_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
        CHUNKED_STATUS,
        None,
        _now(),
    )
    return saved_chunks


async def list_chunks_by_document(
    knowledge_base_repository: KnowledgeBaseRepository,
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> list[Chunk]:
    """列出当前知识库沙箱下某个文档的 chunk。"""
    await _ensure_active_knowledge_base(knowledge_base_repository, kb_id, user_id)
    document = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if document is None:
        raise DocumentNotFoundError("Document not found")
    return await chunk_repository.list_by_document(user_id, kb_id, document_id)


async def embed_document_chunks(
    knowledge_base_repository: KnowledgeBaseRepository,
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    embedding_service: EmbeddingService,
    vector_service: VectorService,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> list[Chunk]:
    """把当前文档下待处理 chunks 写入 Milvus，并回写 vector_id。"""
    await _ensure_active_knowledge_base(knowledge_base_repository, kb_id, user_id)
    document = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if document is None:
        raise DocumentNotFoundError("Document not found")
    if document.status != CHUNKED_STATUS:
        raise ValueError(DOCUMENT_MUST_BE_CHUNKED_MESSAGE)

    pending_chunks = await chunk_repository.list_pending_for_embedding(
        user_id,
        kb_id,
        document_id,
    )
    if not pending_chunks:
        raise ValueError(NO_CHUNKS_AVAILABLE_FOR_EMBEDDING_MESSAGE)

    embeddings = embedding_service.embed_texts(
        [chunk.content for chunk in pending_chunks]
    )
    vector_ids = vector_service.insert_chunk_embeddings(pending_chunks, embeddings)
    embedded_chunks: list[Chunk] = []
    for chunk, vector_id in zip(pending_chunks, vector_ids, strict=True):
        updated_chunk = await chunk_repository.update_embedding_result(
            user_id,
            kb_id,
            chunk.id,
            vector_id,
            _now(),
        )
        if updated_chunk is not None:
            embedded_chunks.append(updated_chunk)

    await document_repository.update_status_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
        EMBEDDED_STATUS,
        None,
        _now(),
    )
    return embedded_chunks


async def get_document_embedding_status(
    knowledge_base_repository: KnowledgeBaseRepository,
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, int | str]:
    """返回指定文档的 embedding 进度统计。"""
    await _ensure_active_knowledge_base(knowledge_base_repository, kb_id, user_id)
    document = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if document is None:
        raise DocumentNotFoundError("Document not found")

    stats = await chunk_repository.count_embedding_status(user_id, kb_id, document_id)
    return {
        "document_id": document_id,
        "status": document.status,
        **stats,
    }


async def _ensure_active_knowledge_base(
    knowledge_base_repository: KnowledgeBaseRepository,
    kb_id: str,
    user_id: str,
) -> None:
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        user_id,
    )
    if knowledge_base is None:
        raise KnowledgeBaseNotFoundError("Knowledge base not found")


def _build_chunks_from_sections(
    sections: list[dict[str, Any]],
    user_id: str,
    kb_id: str,
    document_id: str,
) -> list[Chunk]:
    """把 parsed JSON sections 转成 chunk 实体。"""
    chunks: list[Chunk] = []
    now = _now()
    for section in sections:
        content = str(section.get("content") or "").strip()
        if not content:
            continue

        chunks.append(
            Chunk(
                id=f"chunk_{uuid4().hex}",
                user_id=user_id,
                knowledge_base_id=kb_id,
                document_id=document_id,
                chunk_index=len(chunks),
                title=_optional_str(section.get("title")),
                content=content,
                chapter=_optional_str(section.get("chapter")),
                section=_optional_str(section.get("section")),
                subsection=_optional_str(section.get("subsection")),
                status=CHUNK_CREATED_STATUS,
                vector_id=None,
                created_at=now,
                updated_at=now,
            )
        )
    return chunks


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
