from typing import Protocol

import aiomysql

from app.models.knowledge_base import KnowledgeBase


class KnowledgeBaseRepository(Protocol):
    """知识库 service 层依赖的数据存储接口约定。"""

    async def insert(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        raise NotImplementedError

    async def list_active_by_user(self, user_id: str) -> list[KnowledgeBase]:
        raise NotImplementedError


class MySQLKnowledgeBaseRepository:
    """知识库持久化的 MySQL 实现。"""

    def __init__(self, connection: aiomysql.Connection):
        self.connection = connection

    async def insert(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        """保存一条知识库记录，并返回已保存的实体。"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO knowledge_bases (
                    id,
                    user_id,
                    name,
                    description,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    knowledge_base.id,
                    knowledge_base.user_id,
                    knowledge_base.name,
                    knowledge_base.description,
                    knowledge_base.status,
                    knowledge_base.created_at,
                    knowledge_base.updated_at,
                ),
            )
        await self.connection.commit()
        return knowledge_base

    async def list_active_by_user(self, user_id: str) -> list[KnowledgeBase]:
        """查询某个逻辑用户拥有的 active 状态知识库。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    name,
                    description,
                    status,
                    created_at,
                    updated_at
                FROM knowledge_bases
                WHERE user_id = %s AND status = 'active'
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: dict[str, object]) -> KnowledgeBase:
        """将 aiomysql DictCursor 返回的行数据转换为内部实体。"""
        return KnowledgeBase(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            name=str(row["name"]),
            description=(
                None if row["description"] is None else str(row["description"])
            ),
            status=str(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
