from typing import Protocol

import aiomysql

from app.models.knowledge_base import KnowledgeBase


class KnowledgeBaseRepository(Protocol):
    """知识库 service 层依赖的数据存储接口约定。"""

    async def insert(self, knowledge_base: KnowledgeBase) -> KnowledgeBase:
        raise NotImplementedError

    async def list_active_by_user(self, user_id: str) -> list[KnowledgeBase]:
        raise NotImplementedError

    async def get_active_by_id_and_user(
        self,
        kb_id: str,
        user_id: str,
    ) -> KnowledgeBase | None:
        raise NotImplementedError

    async def list_active_by_ids_and_user(
        self,
        kb_ids: list[str],
        user_id: str,
    ) -> list[KnowledgeBase]:
        raise NotImplementedError

    async def update_active_by_id_and_user(
        self,
        kb_id: str,
        user_id: str,
        updates: dict[str, object],
    ) -> KnowledgeBase | None:
        raise NotImplementedError

    async def delete_active_by_id_and_user(
        self,
        kb_id: str,
        user_id: str,
    ) -> KnowledgeBase | None:
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

    async def get_active_by_id_and_user(
        self,
        kb_id: str,
        user_id: str,
    ) -> KnowledgeBase | None:
        """按知识库沙箱边界查询单条记录。

        这里同时限制 id、user_id、status，避免用户通过猜测 kb_id 访问到
        其他用户或已归档的知识库。
        """
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
                WHERE id = %s AND user_id = %s AND status = 'active'
                LIMIT 1
                """,
                (kb_id, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._from_row(row)

    async def list_active_by_ids_and_user(
        self,
        kb_ids: list[str],
        user_id: str,
    ) -> list[KnowledgeBase]:
        """批量查询当前用户 active 知识库，用于多知识库 RAG 校验。"""
        if not kb_ids:
            return []

        placeholders = ", ".join(["%s"] * len(kb_ids))
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                f"""
                SELECT
                    id,
                    user_id,
                    name,
                    description,
                    status,
                    created_at,
                    updated_at
                FROM knowledge_bases
                WHERE user_id = %s
                  AND status = 'active'
                  AND id IN ({placeholders})
                """,
                (user_id, *kb_ids),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def update_active_by_id_and_user(
        self,
        kb_id: str,
        user_id: str,
        updates: dict[str, object],
    ) -> KnowledgeBase | None:
        """只更新当前用户 active 知识库允许变更的字段。

        service 层已经把 updates 限制为 name、description、updated_at；
        SQL 层再次限制 id、user_id、status，形成最后一道沙箱边界。
        """
        if not updates:
            return await self.get_active_by_id_and_user(kb_id, user_id)

        allowed_fields = ("name", "description", "updated_at")
        assignments = [
            f"{field_name} = %s"
            for field_name in allowed_fields
            if field_name in updates
        ]
        values = [
            updates[field_name]
            for field_name in allowed_fields
            if field_name in updates
        ]
        values.extend([kb_id, user_id])

        async with self.connection.cursor() as cursor:
            await cursor.execute(
                f"""
                UPDATE knowledge_bases
                SET {", ".join(assignments)}
                WHERE id = %s AND user_id = %s AND status = 'active'
                """,
                tuple(values),
            )
        await self.connection.commit()
        return await self.get_active_by_id_and_user(kb_id, user_id)

    async def delete_active_by_id_and_user(
        self,
        kb_id: str,
        user_id: str,
    ) -> KnowledgeBase | None:
        """硬删除当前用户的 active 知识库。

        MySQL 里 chunks 和 documents 都有外键依赖知识库，所以必须先删从表，
        再删除 knowledge_bases 主记录。
        """
        knowledge_base = await self.get_active_by_id_and_user(kb_id, user_id)
        if knowledge_base is None:
            return None

        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                DELETE results FROM benchmark_case_results AS results
                INNER JOIN benchmark_runs AS runs ON runs.id = results.run_id
                WHERE runs.knowledge_base_id = %s AND runs.user_id = %s
                """,
                (kb_id, user_id),
            )
            await cursor.execute(
                """
                DELETE FROM benchmark_runs
                WHERE knowledge_base_id = %s AND user_id = %s
                """,
                (kb_id, user_id),
            )
            await cursor.execute(
                """
                DELETE FROM benchmark_cases
                WHERE knowledge_base_id = %s AND user_id = %s
                """,
                (kb_id, user_id),
            )
            await cursor.execute(
                """
                DELETE FROM knowledge_base_configs
                WHERE knowledge_base_id = %s
                  AND user_id = %s
                """,
                (kb_id, user_id),
            )
            await cursor.execute(
                """
                DELETE FROM chunks
                WHERE knowledge_base_id = %s
                  AND user_id = %s
                """,
                (kb_id, user_id),
            )
            await cursor.execute(
                """
                DELETE FROM documents
                WHERE knowledge_base_id = %s
                  AND user_id = %s
                """,
                (kb_id, user_id),
            )
            await cursor.execute(
                """
                DELETE FROM knowledge_bases
                WHERE id = %s AND user_id = %s AND status = 'active'
                """,
                (kb_id, user_id),
            )
            affected_rows = cursor.rowcount
        await self.connection.commit()

        if affected_rows == 0:
            return None
        return knowledge_base

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
