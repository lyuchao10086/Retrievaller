from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.qa_record import QaRecord
from app.repositories.qa_record import QaRecordRepository
from app.services.knowledge_base import DEFAULT_USER_ID


async def create_qa_record(
    repository: QaRecordRepository,
    question: str,
    answer: str,
    knowledge_base_ids: list[str],
    sources_json: list[dict[str, Any]],
    user_id: str = DEFAULT_USER_ID,
) -> QaRecord:
    """保存一次成功返回给前端的 RAG 问答记录。"""
    now = _now()
    record = QaRecord(
        id=f"qa_{uuid4().hex}",
        user_id=user_id,
        question=question,
        answer=answer,
        knowledge_base_ids=knowledge_base_ids,
        sources_json=sources_json,
        created_at=now,
        updated_at=now,
    )
    return await repository.insert(record)


async def list_qa_records(
    repository: QaRecordRepository,
    user_id: str = DEFAULT_USER_ID,
    limit: int = 50,
) -> list[QaRecord]:
    """查询当前用户最近的 RAG 问答记录。"""
    return await repository.list_recent_by_user(user_id, limit)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
