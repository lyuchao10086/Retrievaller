from datetime import datetime, timezone
from uuid import uuid4

from app.models.knowledge_base import KnowledgeBase
from app.repositories.knowledge_base import KnowledgeBaseRepository
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate


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


async def get_knowledge_base(
    repository: KnowledgeBaseRepository,
    kb_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> KnowledgeBase | None:
    """查询当前逻辑用户可见的单个 active 知识库。

    返回 None 代表这个 kb_id 不存在、不属于当前用户，或已经不是 active 状态。
    API 层会把 None 转换成 404。
    """
    return await repository.get_active_by_id_and_user(kb_id, user_id)


async def update_knowledge_base(
    repository: KnowledgeBaseRepository,
    kb_id: str,
    payload: KnowledgeBaseUpdate,
    user_id: str = DEFAULT_USER_ID,
) -> KnowledgeBase | None:
    """修改当前逻辑用户可见的 active 知识库。

    先按 id + user_id + active 查询，是为了保持知识库之间的逻辑沙箱隔离；
    只有确认目标可见后，才允许更新 name 和 description。
    """
    existing = await repository.get_active_by_id_and_user(kb_id, user_id)
    if existing is None:
        return None

    updates = payload.model_dump(exclude_unset=True)
    updates["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    return await repository.update_active_by_id_and_user(kb_id, user_id, updates)


async def delete_knowledge_base(
    repository: KnowledgeBaseRepository,
    kb_id: str,
    user_id: str = DEFAULT_USER_ID,
) -> KnowledgeBase | None:
    """硬删除当前逻辑用户可见的 active 知识库。"""
    existing = await repository.get_active_by_id_and_user(kb_id, user_id)
    if existing is None:
        return None

    return await repository.delete_active_by_id_and_user(kb_id, user_id)
