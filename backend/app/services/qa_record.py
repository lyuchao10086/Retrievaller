from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.qa_record import QaRecord
from app.repositories.qa_record import QaRecordRepository
from app.services.knowledge_base import DEFAULT_USER_ID
from app.services.local_llm_service import LocalLLMService


async def create_qa_record(
    repository: QaRecordRepository,
    question: str,
    answer: str,
    knowledge_base_ids: list[str],
    sources_json: list[dict[str, Any]],
    title: str | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> QaRecord:
    """保存一次成功返回给前端的 RAG 问答记录。"""
    now = _now()
    record = QaRecord(
        id=f"qa_{uuid4().hex}",
        user_id=user_id,
        title=normalize_qa_record_title(title or question),
        question=question,
        answer=answer,
        knowledge_base_ids=knowledge_base_ids,
        sources_json=sources_json,
        created_at=now,
        updated_at=now,
    )
    return await repository.insert(record)


async def generate_qa_record_title(
    llm_service: LocalLLMService,
    question: str,
    answer: str,
) -> str:
    """用本地大模型把问答记录压缩成侧边栏短标题。"""
    try:
        raw_title = await llm_service.generate_answer(
            "你是问答系统的标题生成器。只输出一个中文短标题，不要解释，不要标点包裹。",
            (
                "请根据下面的一轮问答生成一个适合历史对话列表展示的短标题，"
                "要求 6 到 14 个汉字或等长短语。\n\n"
                f"问题：{question}\n\n回答：{answer[:800]}"
            ),
        )
    except Exception:
        return normalize_qa_record_title(question)

    return normalize_qa_record_title(raw_title)


def normalize_qa_record_title(value: str) -> str:
    title = " ".join(value.strip().strip("\"'“”‘’`").split())
    if not title:
        return "新对话"
    return title[:24]


async def list_qa_records(
    repository: QaRecordRepository,
    user_id: str = DEFAULT_USER_ID,
    limit: int = 50,
) -> list[QaRecord]:
    """查询当前用户最近的 RAG 问答记录。"""
    return await repository.list_recent_by_user(user_id, limit)


async def delete_qa_record(
    repository: QaRecordRepository,
    qa_record_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> QaRecord | None:
    """硬删除当前用户的一条 RAG 问答记录。"""
    return await repository.delete_by_id_and_user(qa_record_id, user_id)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
