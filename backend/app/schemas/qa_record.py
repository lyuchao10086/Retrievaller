from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class QaRecordResponse(BaseModel):
    """问答记录列表接口返回结构。"""

    id: str
    question: str
    answer: str
    knowledge_base_ids: list[str]
    sources_json: list[dict[str, Any]]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
