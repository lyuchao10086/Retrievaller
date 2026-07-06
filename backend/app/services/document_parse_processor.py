import json
from datetime import datetime, timezone
from pathlib import Path

from app.models.document import Document
from app.repositories.document import DocumentRepository
from app.services.document import FAILED_STATUS, PARSED_STATUS, PARSING_STATUS
from app.services.document_storage import DocumentStorage
from app.services.parsers.markdown_parser import parse_markdown_document


PARSED_RESULTS_BUCKET = "rag-parsed-results"
UNSUPPORTED_FILE_TYPE_MESSAGE = "Unsupported file type for current parser"
MARKDOWN_SUFFIXES = {".md", ".markdown"}


async def process_document_parse(
    document_repository: DocumentRepository,
    storage: DocumentStorage,
    kb_id: str,
    document_id: str,
    user_id: str,
    parsed_bucket: str = PARSED_RESULTS_BUCKET,
) -> Document | None:
    """执行后台文档解析。

    当前只支持 Markdown：从 MinIO 读取原文，解析结构化 JSON，再写回 MinIO。
    """
    document = await document_repository.get_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
    )
    if document is None:
        return None

    parsing_document = await document_repository.update_status_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
        PARSING_STATUS,
        None,
        _now(),
    )
    if parsing_document is None:
        return None

    try:
        if not _is_markdown_file(document.file_name):
            return await _mark_failed(
                document_repository,
                user_id,
                kb_id,
                document_id,
                UNSUPPORTED_FILE_TYPE_MESSAGE,
            )

        raw_bytes = await storage.get_object(
            document.storage_bucket,
            document.storage_object_key,
        )
        markdown_text = raw_bytes.decode("utf-8")
        parsed_json = parse_markdown_document(
            markdown_text,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            file_name=document.file_name,
            file_type=document.file_type,
        )
        parsed_object_key = (
            f"users/{user_id}/knowledge_bases/{kb_id}/parsed/{document_id}.json"
        )
        parsed_bytes = json.dumps(
            parsed_json,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

        await storage.ensure_bucket(parsed_bucket)
        await storage.put_object(
            parsed_bucket,
            parsed_object_key,
            parsed_bytes,
            "application/json",
        )
        return await document_repository.set_parse_result_by_id_and_knowledge_base(
            user_id,
            kb_id,
            document_id,
            parsed_bucket,
            parsed_object_key,
            PARSED_STATUS,
            None,
            _now(),
        )
    except Exception as exc:
        return await _mark_failed(
            document_repository,
            user_id,
            kb_id,
            document_id,
            str(exc),
        )


def _is_markdown_file(file_name: str) -> bool:
    """按文件名后缀判断当前阶段是否支持解析。"""
    return Path(file_name).suffix.lower() in MARKDOWN_SUFFIXES


async def _mark_failed(
    document_repository: DocumentRepository,
    user_id: str,
    kb_id: str,
    document_id: str,
    error_message: str,
) -> Document | None:
    """把文档标记为解析失败，并清空本次解析结果位置。"""
    return await document_repository.set_parse_result_by_id_and_knowledge_base(
        user_id,
        kb_id,
        document_id,
        None,
        None,
        FAILED_STATUS,
        error_message,
        _now(),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
