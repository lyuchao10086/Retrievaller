from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class KnowledgeBase:
    """知识库内部实体，用于 service 层和 repository 层之间传递数据。"""

    id: str
    user_id: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
