from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class KnowledgeBase:
    """Internal knowledge base entity used between service and repository layers."""

    id: str
    user_id: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
