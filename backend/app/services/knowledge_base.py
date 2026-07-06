from datetime import datetime, timezone
from uuid import uuid4

from app.models.knowledge_base import KnowledgeBase
from app.repositories.knowledge_base import KnowledgeBaseRepository
from app.schemas.knowledge_base import KnowledgeBaseCreate


DEFAULT_USER_ID = "default_user"
ACTIVE_STATUS = "active"


async def create_knowledge_base(
    repository: KnowledgeBaseRepository,
    payload: KnowledgeBaseCreate,
    user_id: str = DEFAULT_USER_ID,
) -> KnowledgeBase:
    """Create a sandbox root for future documents, chunks, vectors, and chats."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    knowledge_base = KnowledgeBase(
        id=f"kb_{uuid4().hex}",
        user_id=user_id,
        name=payload.name,
        description=payload.description,
        status=ACTIVE_STATUS,
        created_at=now,
        updated_at=now,
    )
    return await repository.insert(knowledge_base)


async def list_knowledge_bases(
    repository: KnowledgeBaseRepository,
    user_id: str = DEFAULT_USER_ID,
) -> list[KnowledgeBase]:
    """Return active knowledge bases visible to the current logical user."""
    return await repository.list_active_by_user(user_id)
