from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class QaRecord:
    """RAG 问答记录内部实体。

    记录只保存成功返回给前端的问答结果，不参与多轮上下文。
    """

    id: str
    user_id: str
    question: str
    answer: str
    knowledge_base_ids: list[str]
    sources_json: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
