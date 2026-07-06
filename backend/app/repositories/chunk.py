from datetime import datetime
from typing import Protocol

import aiomysql

from app.models.chunk import Chunk


class ChunkRepository(Protocol):
    """chunk service 层依赖的数据存储接口约定。"""

    async def insert_many(self, chunks: list[Chunk]) -> list[Chunk]:
        raise NotImplementedError

    async def list_by_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> list[Chunk]:
        raise NotImplementedError

    async def exists_by_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> bool:
        raise NotImplementedError

    async def list_pending_for_embedding(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> list[Chunk]:
        raise NotImplementedError

    async def update_embedding_result(
        self,
        user_id: str,
        knowledge_base_id: str,
        chunk_id: str,
        vector_id: str,
        updated_at: datetime,
    ) -> Chunk | None:
        raise NotImplementedError

    async def count_embedding_status(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> dict[str, int]:
        raise NotImplementedError


class MySQLChunkRepository:
    """chunk 持久化的 MySQL 实现。"""

    def __init__(self, connection: aiomysql.Connection):
        self.connection = connection

    async def insert_many(self, chunks: list[Chunk]) -> list[Chunk]:
        """批量保存一个文档下生成的 chunk。"""
        if not chunks:
            return []

        async with self.connection.cursor() as cursor:
            await cursor.executemany(
                """
                INSERT INTO chunks (
                    id,
                    user_id,
                    knowledge_base_id,
                    document_id,
                    chunk_index,
                    title,
                    content,
                    chapter,
                    section,
                    subsection,
                    status,
                    vector_id,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        chunk.id,
                        chunk.user_id,
                        chunk.knowledge_base_id,
                        chunk.document_id,
                        chunk.chunk_index,
                        chunk.title,
                        chunk.content,
                        chunk.chapter,
                        chunk.section,
                        chunk.subsection,
                        chunk.status,
                        chunk.vector_id,
                        chunk.created_at,
                        chunk.updated_at,
                    )
                    for chunk in chunks
                ],
            )
        await self.connection.commit()
        return chunks

    async def list_by_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> list[Chunk]:
        """查询当前用户在指定知识库、指定文档下的 chunk。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    knowledge_base_id,
                    document_id,
                    chunk_index,
                    title,
                    content,
                    chapter,
                    section,
                    subsection,
                    status,
                    vector_id,
                    created_at,
                    updated_at
                FROM chunks
                WHERE user_id = %s
                  AND knowledge_base_id = %s
                  AND document_id = %s
                ORDER BY chunk_index ASC
                """,
                (user_id, knowledge_base_id, document_id),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def exists_by_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> bool:
        """判断指定文档是否已经生成过 chunk。"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT 1
                FROM chunks
                WHERE user_id = %s
                  AND knowledge_base_id = %s
                  AND document_id = %s
                LIMIT 1
                """,
                (user_id, knowledge_base_id, document_id),
            )
            row = await cursor.fetchone()
        return row is not None

    async def list_pending_for_embedding(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> list[Chunk]:
        """查询还没有写入向量库的 chunk。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    knowledge_base_id,
                    document_id,
                    chunk_index,
                    title,
                    content,
                    chapter,
                    section,
                    subsection,
                    status,
                    vector_id,
                    created_at,
                    updated_at
                FROM chunks
                WHERE user_id = %s
                  AND knowledge_base_id = %s
                  AND document_id = %s
                  AND status = 'created'
                  AND vector_id IS NULL
                ORDER BY chunk_index ASC
                """,
                (user_id, knowledge_base_id, document_id),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def update_embedding_result(
        self,
        user_id: str,
        knowledge_base_id: str,
        chunk_id: str,
        vector_id: str,
        updated_at: datetime,
    ) -> Chunk | None:
        """回写 chunk 的 Milvus vector_id，并标记为 embedded。"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE chunks
                SET vector_id = %s,
                    status = 'embedded',
                    updated_at = %s
                WHERE id = %s
                  AND user_id = %s
                  AND knowledge_base_id = %s
                """,
                (vector_id, updated_at, chunk_id, user_id, knowledge_base_id),
            )
            affected_rows = cursor.rowcount
        await self.connection.commit()

        if affected_rows == 0:
            return None
        return await self._get_by_id(user_id, knowledge_base_id, chunk_id)

    async def count_embedding_status(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> dict[str, int]:
        """统计指定文档下 chunk 的 embedding 进度。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_chunks,
                    SUM(
                        CASE
                            WHEN status = 'embedded' AND vector_id IS NOT NULL
                            THEN 1 ELSE 0
                        END
                    ) AS embedded_chunks
                FROM chunks
                WHERE user_id = %s
                  AND knowledge_base_id = %s
                  AND document_id = %s
                """,
                (user_id, knowledge_base_id, document_id),
            )
            row = await cursor.fetchone()

        total_chunks = int(row["total_chunks"] or 0)
        embedded_chunks = int(row["embedded_chunks"] or 0)
        return {
            "total_chunks": total_chunks,
            "embedded_chunks": embedded_chunks,
            "pending_chunks": total_chunks - embedded_chunks,
        }

    async def _get_by_id(
        self,
        user_id: str,
        knowledge_base_id: str,
        chunk_id: str,
    ) -> Chunk | None:
        """按沙箱条件查询单个 chunk。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    knowledge_base_id,
                    document_id,
                    chunk_index,
                    title,
                    content,
                    chapter,
                    section,
                    subsection,
                    status,
                    vector_id,
                    created_at,
                    updated_at
                FROM chunks
                WHERE id = %s
                  AND user_id = %s
                  AND knowledge_base_id = %s
                LIMIT 1
                """,
                (chunk_id, user_id, knowledge_base_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._from_row(row)

    @staticmethod
    def _from_row(row: dict[str, object]) -> Chunk:
        """将 MySQL 行数据转换成内部实体。"""
        return Chunk(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            knowledge_base_id=str(row["knowledge_base_id"]),
            document_id=str(row["document_id"]),
            chunk_index=int(row["chunk_index"]),
            title=None if row["title"] is None else str(row["title"]),
            content=str(row["content"]),
            chapter=None if row["chapter"] is None else str(row["chapter"]),
            section=None if row["section"] is None else str(row["section"]),
            subsection=(
                None if row["subsection"] is None else str(row["subsection"])
            ),
            status=str(row["status"]),
            vector_id=None if row["vector_id"] is None else str(row["vector_id"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
