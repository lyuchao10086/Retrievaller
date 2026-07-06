from typing import Annotated

import aiomysql
from fastapi import APIRouter, Depends, status

from app.core.database import get_db_connection
from app.repositories.knowledge_base import (
    KnowledgeBaseRepository,
    MySQLKnowledgeBaseRepository,
)
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseResponse
from app.services.knowledge_base import create_knowledge_base, list_knowledge_bases


router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


async def get_knowledge_base_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> KnowledgeBaseRepository:
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
    knowledge_base = await create_knowledge_base(repository, payload)
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases_api(
    repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
) -> list[KnowledgeBaseResponse]:
    knowledge_bases = await list_knowledge_bases(repository)
    return [
        KnowledgeBaseResponse.model_validate(knowledge_base)
        for knowledge_base in knowledge_bases
    ]
