from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import uuid4

from app.models.chunk import Chunk
from app.models.document import Document
from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.repositories.knowledge_base import KnowledgeBaseRepository
from app.services.document_storage import DocumentStorage
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_base import DEFAULT_USER_ID
from app.services.vector_service import VectorService


DEFAULT_DOCUMENT_BUCKET = "rag-documents"
DEFAULT_PARSED_RESULTS_BUCKET = "rag-parsed-results"
UPLOADED_STATUS = "uploaded"
PARSING_STATUS = "parsing"
PARSED_STATUS = "parsed"
CHUNKED_STATUS = "chunked"
EMBEDDING_STATUS = "embedding"
EMBEDDED_STATUS = "embedded"
FAILED_STATUS = "failed"
CREATED_CHUNK_STATUS = "created"
DEFAULT_FILE_TYPE = "application/octet-stream"
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
SUPPORTED_TEXT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
}


class KnowledgeBaseNotFoundError(LookupError):
    """当前用户下找不到 active 知识库。"""


class DocumentNotFoundError(LookupError):
    """当前知识库沙箱下找不到可见文档。"""


class UnsupportedDocumentTypeError(ValueError):
    """当前最小闭环暂不支持该文档类型解析。"""


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


async def rename_document(
    document_repository: DocumentRepository,
    kb_id: str,
    document_id: str,
    new_file_name: str,
    user_id: str = DEFAULT_USER_ID,
) -> Document | None:
    """重命名指定知识库下的文档文件名。"""
    existing = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if existing is None:
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return await document_repository.rename_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
        new_file_name,
        now,
    )


def parse_document_content(
    content: bytes,
    file_name: str,
    file_type: str | None,
) -> dict[str, object]:
    """解析 txt/markdown 内容为统一 sections 结构。

    PDF、OCR、Office 等格式后续可在这里扩展 parser 分支。
    """
    if not is_supported_text_document(file_name, file_type):
        raise UnsupportedDocumentTypeError(
            "Only txt, md and markdown documents are supported"
        )

    text = content.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    suffix = Path(file_name).suffix.lower()
    normalized_file_type = (file_type or "").split(";")[0].strip().lower()
    if suffix in {".md", ".markdown"} or normalized_file_type in {
        "text/markdown",
        "text/x-markdown",
    }:
        return {
            "parser": "markdown",
            "sections": _parse_markdown_sections(text),
        }

    return {
        "parser": "plain_text",
        "sections": [
            {"content": paragraph}
            for paragraph in _split_paragraphs(text)
        ],
    }


def is_supported_text_document(file_name: str, file_type: str | None) -> bool:
    """判断文档是否属于当前后台处理闭环支持的纯文本类型。"""
    suffix = Path(file_name).suffix.lower()
    normalized_file_type = (file_type or "").split(";")[0].strip().lower()
    return (
        suffix in SUPPORTED_TEXT_EXTENSIONS
        or normalized_file_type in SUPPORTED_TEXT_MIME_TYPES
    )


async def parse_document_to_storage(
    document_repository: DocumentRepository,
    storage: DocumentStorage,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
    parsed_bucket_name: str = DEFAULT_PARSED_RESULTS_BUCKET,
) -> dict[str, object]:
    """同步解析文档并把解析 JSON 写入对象存储。

    当前实现是同步接口版本；后续迁移到 Celery 时可把本函数作为 task 主体复用。
    """
    document = await _require_document(document_repository, kb_id, document_id, user_id)
    await _update_document_status(
        document_repository,
        kb_id,
        document_id,
        PARSING_STATUS,
        None,
        user_id,
    )
    try:
        raw_content = await storage.get_object(
            document.storage_bucket,
            document.storage_object_key,
        )
        parsed = parse_document_content(
            raw_content,
            document.file_name,
            document.file_type,
        )
        payload = {
            "document_id": document.id,
            "knowledge_base_id": document.knowledge_base_id,
            "file_name": document.file_name,
            "file_type": document.file_type,
            **parsed,
        }
        parsed_object_key = (
            f"users/{user_id}/knowledge_bases/{kb_id}/parsed/"
            f"{document_id}.json"
        )
        await storage.ensure_bucket(parsed_bucket_name)
        await storage.put_object(
            parsed_bucket_name,
            parsed_object_key,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json",
        )
        updated_at = _utc_now()
        await document_repository.set_parse_result_by_id_and_knowledge_base(
            user_id,
            kb_id,
            document_id,
            parsed_bucket_name,
            parsed_object_key,
            PARSED_STATUS,
            None,
            updated_at,
        )
        return payload
    except Exception as exc:
        await _update_document_status(
            document_repository,
            kb_id,
            document_id,
            FAILED_STATUS,
            str(exc),
            user_id,
        )
        raise


async def get_parsed_document_payload(
    document_repository: DocumentRepository,
    storage: DocumentStorage,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, object]:
    """读取指定文档的解析结果 JSON。"""
    document = await _require_document(document_repository, kb_id, document_id, user_id)
    if not document.parsed_bucket or not document.parsed_object_key:
        raise FileNotFoundError("Parsed document not found")
    content = await storage.get_object(document.parsed_bucket, document.parsed_object_key)
    return json.loads(content.decode("utf-8"))


async def create_document_chunks(
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    storage: DocumentStorage,
    kb_id: str,
    document_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    separator: str | None = None,
    replace_consecutive_whitespace: bool = False,
    remove_urls_and_emails: bool = False,
    user_id: str = DEFAULT_USER_ID,
) -> list[Chunk]:
    """从解析结果生成 chunks 并写入 chunks 表。"""
    document = await _require_document(document_repository, kb_id, document_id, user_id)
    if document.status not in {PARSED_STATUS, CHUNKED_STATUS, EMBEDDED_STATUS}:
        raise ValueError("Document must be parsed before chunking")

    parsed = await get_parsed_document_payload(
        document_repository,
        storage,
        kb_id,
        document_id,
        user_id,
    )
    chunks = _build_chunks_from_parsed_payload(
        parsed,
        document,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separator=separator,
        replace_consecutive_whitespace=replace_consecutive_whitespace,
        remove_urls_and_emails=remove_urls_and_emails,
    )
    saved_chunks = await chunk_repository.replace_by_document(
        user_id,
        kb_id,
        document_id,
        chunks,
    )
    await _update_document_status(
        document_repository,
        kb_id,
        document_id,
        CHUNKED_STATUS,
        None,
        user_id,
    )
    return saved_chunks


async def list_document_chunks(
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> list[Chunk]:
    """列出指定文档的 chunks。"""
    await _require_document(document_repository, kb_id, document_id, user_id)
    return await chunk_repository.list_by_document(user_id, kb_id, document_id)


async def embed_document_chunks(
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    embedding_service: EmbeddingService,
    vector_service: VectorService,
    kb_id: str,
    document_id: str,
    expected_embedding_dimension: int | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, int | str]:
    """为文档 chunks 生成 embedding，写入 Milvus，并回写 chunks 状态。"""
    document = await _require_document(document_repository, kb_id, document_id, user_id)
    if document.status not in {CHUNKED_STATUS, EMBEDDING_STATUS, EMBEDDED_STATUS}:
        raise ValueError("Document must be chunked before embedding")

    chunks = await chunk_repository.list_by_document(user_id, kb_id, document_id)
    if not chunks:
        raise ValueError("Document has no chunks to embed")

    await _update_document_status(
        document_repository,
        kb_id,
        document_id,
        EMBEDDING_STATUS,
        None,
        user_id,
    )
    try:
        embeddings = embedding_service.embed_texts([chunk.content for chunk in chunks])
        _validate_embeddings(embeddings, len(chunks), expected_embedding_dimension)
        vector_service.delete_chunk_embeddings_by_document(user_id, kb_id, document_id)
        vector_ids = vector_service.insert_chunk_embeddings(chunks, embeddings)
        if len(vector_ids) != len(chunks):
            raise ValueError("Vector service returned unexpected vector_id count")
        updated_at = _utc_now()
        await chunk_repository.update_embedding_results(
            user_id,
            kb_id,
            document_id,
            list(zip([chunk.id for chunk in chunks], vector_ids)),
            updated_at,
        )
        await _update_document_status(
            document_repository,
            kb_id,
            document_id,
            EMBEDDED_STATUS,
            None,
            user_id,
        )
        return await get_document_embedding_status(
            document_repository,
            chunk_repository,
            kb_id,
            document_id,
            user_id,
        )
    except Exception as exc:
        await _update_document_status(
            document_repository,
            kb_id,
            document_id,
            FAILED_STATUS,
            str(exc),
            user_id,
        )
        raise


async def get_document_embedding_status(
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    kb_id: str,
    document_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, int | str]:
    """返回前端期望的 embedding 进度结构。"""
    document = await _require_document(document_repository, kb_id, document_id, user_id)
    counts = await chunk_repository.count_embedding_status(user_id, kb_id, document_id)
    return {
        "document_id": document_id,
        "status": document.status,
        **counts,
    }


def _parse_markdown_sections(text: str) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    content_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current, content_lines
        if current is None:
            paragraph_content = "\n".join(_compact_markdown_lines(content_lines))
            if paragraph_content:
                sections.append({"content": paragraph_content})
        else:
            current["content"] = "\n".join(_compact_markdown_lines(content_lines))
            sections.append(current)
        current = None
        content_lines = []

    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            level = len(stripped) - len(stripped.lstrip("#"))
            if heading_text and 1 <= level <= 6:
                flush_current()
                current = {"level": level, "title": heading_text}
                continue
        content_lines.append(raw_line)

    flush_current()
    return sections


def _split_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append("\n".join(current))
                current = []
            continue
        current.append(stripped)
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def _compact_markdown_lines(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


def _build_chunks_from_parsed_payload(
    parsed: dict[str, object],
    document: Document,
    chunk_size: int,
    chunk_overlap: int,
    separator: str | None = None,
    replace_consecutive_whitespace: bool = False,
    remove_urls_and_emails: bool = False,
) -> list[Chunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be greater than or equal to 0 and less than chunk_size")

    now = _utc_now()
    chunks: list[Chunk] = []
    sections = parsed.get("sections")
    if not isinstance(sections, list):
        sections = []

    for section in sections:
        if not isinstance(section, dict):
            continue
        content = str(section.get("content") or "").strip()
        if not content:
            continue
        for segment in _split_content_by_separator(content, separator):
            cleaned_segment = _clean_chunk_text(
                segment,
                replace_consecutive_whitespace=replace_consecutive_whitespace,
                remove_urls_and_emails=remove_urls_and_emails,
            )
            if not cleaned_segment:
                continue
            for piece in _split_text_to_chunks(cleaned_segment, chunk_size, chunk_overlap):
                chunks.append(
                    Chunk(
                        id=f"chunk_{uuid4().hex}",
                        user_id=document.user_id,
                        knowledge_base_id=document.knowledge_base_id,
                        document_id=document.id,
                        chunk_index=len(chunks),
                        title=_optional_str(section.get("title")),
                        content=piece,
                        chapter=_section_heading(section, 1),
                        section=_section_heading(section, 2),
                        subsection=_section_heading(section, 3),
                        status=CREATED_CHUNK_STATUS,
                        vector_id=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
    return chunks


def _split_content_by_separator(text: str, separator: str | None) -> list[str]:
    normalized_separator = _normalize_separator(separator)
    if not normalized_separator:
        return [text]
    return [part for part in text.split(normalized_separator) if part.strip()]


def _normalize_separator(separator: str | None) -> str | None:
    if separator is None:
        return None
    normalized = (
        separator
        .replace("\\r", "\r")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
    )
    return normalized or None


def _clean_chunk_text(
    text: str,
    replace_consecutive_whitespace: bool,
    remove_urls_and_emails: bool,
) -> str:
    cleaned = text
    if remove_urls_and_emails:
        cleaned = re.sub(r"https?://\S+|www\.\S+", " ", cleaned)
        cleaned = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", " ", cleaned)
    if replace_consecutive_whitespace:
        cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _split_text_to_chunks(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    step = chunk_size - chunk_overlap
    start = 0
    while start < len(text):
        piece = text[start:start + chunk_size].strip()
        if piece:
            chunks.append(piece)
        start += step
    return chunks


def _section_heading(section: dict[str, object], expected_level: int) -> str | None:
    if section.get("level") == expected_level:
        return _optional_str(section.get("title"))
    return _optional_str(section.get(("chapter", "section", "subsection")[expected_level - 1]))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validate_embeddings(
    embeddings: list[list[float]],
    expected_count: int,
    expected_dimension: int | None,
) -> None:
    if len(embeddings) != expected_count:
        raise ValueError("Embedding service returned unexpected embedding count")
    if expected_dimension is None:
        return
    for embedding in embeddings:
        if len(embedding) != expected_dimension:
            raise ValueError(
                "Embedding dimension mismatch: "
                f"expected {expected_dimension}, got {len(embedding)}"
            )


async def _require_document(
    document_repository: DocumentRepository,
    kb_id: str,
    document_id: str,
    user_id: str,
) -> Document:
    document = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if document is None:
        raise DocumentNotFoundError("Document not found")
    return document


async def _update_document_status(
    document_repository: DocumentRepository,
    kb_id: str,
    document_id: str,
    status: str,
    error_message: str | None,
    user_id: str,
) -> Document | None:
    return await document_repository.update_status_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
        status,
        error_message,
        _utc_now(),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
