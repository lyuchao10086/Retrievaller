from typing import Annotated

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_db_connection
from app.repositories.knowledge_base import (
    KnowledgeBaseRepository,
    MySQLKnowledgeBaseRepository,
)
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.services.knowledge_base import (
    create_knowledge_base,
    delete_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    update_knowledge_base,
)


router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


async def get_knowledge_base_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> KnowledgeBaseRepository:
    """将当前请求的 MySQL 连接包装成 repository 实例。"""
    return MySQLKnowledgeBaseRepository(connection)


@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base_api(
    payload: KnowledgeBaseCreate,
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
) -> KnowledgeBaseResponse:
    """为默认用户创建一个 active 状态的知识库。"""
    knowledge_base = await create_knowledge_base(repository, payload)
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases_api(
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
) -> list[KnowledgeBaseResponse]:
    """列出默认用户下 active 状态的知识库。"""
    knowledge_bases = await list_knowledge_bases(repository)
    return [
        KnowledgeBaseResponse.model_validate(knowledge_base)
        for knowledge_base in knowledge_bases
    ]


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base_api(
    kb_id: str,
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
) -> KnowledgeBaseResponse:
    """查询默认用户可见的单个 active 知识库，查不到时返回 404。"""
    knowledge_base = await get_knowledge_base(repository, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base_api(
    kb_id: str,
    payload: KnowledgeBaseUpdate,
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
) -> KnowledgeBaseResponse:
    """修改默认用户可见的 active 知识库，查不到时返回 404。"""
    knowledge_base = await update_knowledge_base(repository, kb_id, payload)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.delete("/{kb_id}", response_model=KnowledgeBaseResponse)
async def delete_knowledge_base_api(
    kb_id: str,
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
) -> KnowledgeBaseResponse:
    """软删除默认用户可见的 active 知识库，查不到时返回 404。"""
    knowledge_base = await delete_knowledge_base(repository, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return KnowledgeBaseResponse.model_validate(knowledge_base)
