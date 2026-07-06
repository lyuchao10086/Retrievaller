from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class KnowledgeBase:
    id: str
    user_id: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
