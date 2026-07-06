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
    """创建知识库沙箱根节点，后续文档、chunk、向量和问答都会归属于它。"""
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
    """返回当前逻辑用户可见的 active 状态知识库。"""
    return await repository.list_active_by_user(user_id)
