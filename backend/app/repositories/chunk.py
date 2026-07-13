from typing import Protocol

import aiomysql

from app.models.chunk import Chunk


class ChunkRepository(Protocol):
    """chunk service 层依赖的数据存储接口约定。"""

    async def replace_by_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        chunks: list[Chunk],
    ) -> list[Chunk]:
        raise NotImplementedError

    async def list_by_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> list[Chunk]:
        raise NotImplementedError

    async def delete_by_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> list[Chunk]:
        raise NotImplementedError

    async def update_embedding_results(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        results: list[tuple[str, str]],
        updated_at,
    ) -> list[Chunk]:
        raise NotImplementedError

    async def count_embedding_status(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> dict[str, int]:
        raise NotImplementedError

    async def list_by_ids(
        self,
        user_id: str,
        knowledge_base_id: str,
        chunk_ids: list[str],
    ) -> list[Chunk]:
        raise NotImplementedError

    async def list_by_ids_and_knowledge_base_ids(
        self,
        user_id: str,
        knowledge_base_ids: list[str],
        chunk_ids: list[str],
    ) -> list[Chunk]:
        raise NotImplementedError

    async def exists_embedded_by_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
    ) -> bool:
        raise NotImplementedError

    async def exists_embedded_by_knowledge_base_ids(
        self,
        user_id: str,
        knowledge_base_ids: list[str],
    ) -> bool:
        raise NotImplementedError


class MySQLChunkRepository:
    """chunk 持久化的 MySQL 实现。"""

    def __init__(self, connection: aiomysql.Connection):
        self.connection = connection

    async def replace_by_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        chunks: list[Chunk],
    ) -> list[Chunk]:
        """删除指定文档旧 chunks，再批量写入新的切分结果。"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                DELETE FROM chunks
                WHERE user_id = %s
                  AND knowledge_base_id = %s
                  AND document_id = %s
                """,
                (user_id, knowledge_base_id, document_id),
            )
            if chunks:
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
        """按文档列出全部 chunks，用于预览和 embedding。"""
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

    async def delete_by_document(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> list[Chunk]:
        """删除指定文档的 chunk 元数据；重复执行时保持幂等。"""
        chunks = await self.list_by_document(user_id, knowledge_base_id, document_id)
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                DELETE FROM chunks
                WHERE user_id = %s
                  AND knowledge_base_id = %s
                  AND document_id = %s
                """,
                (user_id, knowledge_base_id, document_id),
            )
        await self.connection.commit()
        return chunks

    async def update_embedding_results(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        results: list[tuple[str, str]],
        updated_at,
    ) -> list[Chunk]:
        """写回 chunk 对应的 Milvus vector_id，并标记为 embedded。"""
        if not results:
            return await self.list_by_document(user_id, knowledge_base_id, document_id)

        async with self.connection.cursor() as cursor:
            await cursor.executemany(
                """
                UPDATE chunks
                SET vector_id = %s,
                    status = 'embedded',
                    updated_at = %s
                WHERE id = %s
                  AND user_id = %s
                  AND knowledge_base_id = %s
                  AND document_id = %s
                """,
                [
                    (
                        vector_id,
                        updated_at,
                        chunk_id,
                        user_id,
                        knowledge_base_id,
                        document_id,
                    )
                    for chunk_id, vector_id in results
                ],
            )
        await self.connection.commit()
        return await self.list_by_document(user_id, knowledge_base_id, document_id)

    async def count_embedding_status(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> dict[str, int]:
        """统计文档 chunks 的 embedding 进度。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_chunks,
                    SUM(CASE WHEN status = 'embedded' AND vector_id IS NOT NULL THEN 1 ELSE 0 END)
                        AS embedded_chunks
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

    async def list_by_ids(
        self,
        user_id: str,
        knowledge_base_id: str,
        chunk_ids: list[str],
    ) -> list[Chunk]:
        """按 chunk_id 列表批量回查 chunk，并再次带上沙箱条件。"""
        if not chunk_ids:
            return []

        placeholders = ", ".join(["%s"] * len(chunk_ids))
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                f"""
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
                  AND status = 'embedded'
                  AND vector_id IS NOT NULL
                  AND id IN ({placeholders})
                """,
                (user_id, knowledge_base_id, *chunk_ids),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def list_by_ids_and_knowledge_base_ids(
        self,
        user_id: str,
        knowledge_base_ids: list[str],
        chunk_ids: list[str],
    ) -> list[Chunk]:
        """批量回查多个知识库范围内的 chunks，并再次带上沙箱条件。"""
        if not knowledge_base_ids or not chunk_ids:
            return []

        kb_placeholders = ", ".join(["%s"] * len(knowledge_base_ids))
        chunk_placeholders = ", ".join(["%s"] * len(chunk_ids))
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                f"""
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
                  AND knowledge_base_id IN ({kb_placeholders})
                  AND status = 'embedded'
                  AND vector_id IS NOT NULL
                  AND id IN ({chunk_placeholders})
                """,
                (user_id, *knowledge_base_ids, *chunk_ids),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def exists_embedded_by_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
    ) -> bool:
        """判断知识库下是否已有写入向量库的 chunk。"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT 1
                FROM chunks
                WHERE user_id = %s
                  AND knowledge_base_id = %s
                  AND status = 'embedded'
                  AND vector_id IS NOT NULL
                LIMIT 1
                """,
                (user_id, knowledge_base_id),
            )
            row = await cursor.fetchone()
        return row is not None

    async def exists_embedded_by_knowledge_base_ids(
        self,
        user_id: str,
        knowledge_base_ids: list[str],
    ) -> bool:
        """判断多个知识库范围内是否已有可检索向量。"""
        if not knowledge_base_ids:
            return False

        placeholders = ", ".join(["%s"] * len(knowledge_base_ids))
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                f"""
                SELECT 1
                FROM chunks
                WHERE user_id = %s
                  AND knowledge_base_id IN ({placeholders})
                  AND status = 'embedded'
                  AND vector_id IS NOT NULL
                LIMIT 1
                """,
                (user_id, *knowledge_base_ids),
            )
            row = await cursor.fetchone()
        return row is not None

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
