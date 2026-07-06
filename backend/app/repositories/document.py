from datetime import datetime
from typing import Protocol

import aiomysql

from app.models.document import Document


class DocumentRepository(Protocol):
    """文档 service 层依赖的数据存储接口约定。"""

    async def insert(self, document: Document) -> Document:
        raise NotImplementedError

    async def list_by_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
    ) -> list[Document]:
        raise NotImplementedError

    async def get_by_id_and_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> Document | None:
        raise NotImplementedError

    async def soft_delete_by_id_and_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        deleted_at: datetime,
    ) -> Document | None:
        raise NotImplementedError

    async def update_status_by_id_and_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        status: str,
        error_message: str | None,
        updated_at: datetime,
    ) -> Document | None:
        raise NotImplementedError

    async def set_task_id_by_id_and_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        task_id: str,
        updated_at: datetime,
    ) -> Document | None:
        raise NotImplementedError


class MySQLDocumentRepository:
    """文档持久化的 MySQL 实现。"""

    def __init__(self, connection: aiomysql.Connection):
        self.connection = connection

    async def insert(self, document: Document) -> Document:
        """保存上传后的文档元数据记录。"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO documents (
                    id,
                    user_id,
                    knowledge_base_id,
                    file_name,
                    file_type,
                    file_size,
                    storage_bucket,
                    storage_object_key,
                    status,
                    error_message,
                    task_id,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    document.id,
                    document.user_id,
                    document.knowledge_base_id,
                    document.file_name,
                    document.file_type,
                    document.file_size,
                    document.storage_bucket,
                    document.storage_object_key,
                    document.status,
                    document.error_message,
                    document.task_id,
                    document.created_at,
                    document.updated_at,
                ),
            )
        await self.connection.commit()
        return document

    async def list_by_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
    ) -> list[Document]:
        """查询当前用户在指定知识库沙箱下的文档记录。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    knowledge_base_id,
                    file_name,
                    file_type,
                    file_size,
                    storage_bucket,
                    storage_object_key,
                    status,
                    error_message,
                    task_id,
                    created_at,
                    updated_at
                FROM documents
                WHERE user_id = %s
                  AND knowledge_base_id = %s
                  AND status != 'deleted'
                ORDER BY created_at DESC
                """,
                (user_id, knowledge_base_id),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def get_by_id_and_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> Document | None:
        """按 user_id、knowledge_base_id、document_id 查询单个文档。

        这三个条件必须同时存在，防止拿一个 document_id 跨知识库读取元数据。
        """
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    knowledge_base_id,
                    file_name,
                    file_type,
                    file_size,
                    storage_bucket,
                    storage_object_key,
                    status,
                    error_message,
                    task_id,
                    created_at,
                    updated_at
                FROM documents
                WHERE id = %s
                  AND user_id = %s
                  AND knowledge_base_id = %s
                  AND status != 'deleted'
                LIMIT 1
                """,
                (document_id, user_id, knowledge_base_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._from_row(row)

    async def soft_delete_by_id_and_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        deleted_at: datetime,
    ) -> Document | None:
        """软删除指定知识库下的文档元数据。

        这里只更新 documents 表，不删除 MinIO 原始文件、Milvus 向量或未来的 chunk。
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE documents
                SET status = 'deleted', updated_at = %s
                WHERE id = %s
                  AND user_id = %s
                  AND knowledge_base_id = %s
                  AND status != 'deleted'
                """,
                (deleted_at, document_id, user_id, knowledge_base_id),
            )
            affected_rows = cursor.rowcount
        await self.connection.commit()

        if affected_rows == 0:
            return None
        return await self._get_by_id_and_knowledge_base_including_deleted(
            user_id,
            knowledge_base_id,
            document_id,
        )

    async def update_status_by_id_and_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        status: str,
        error_message: str | None,
        updated_at: datetime,
    ) -> Document | None:
        """更新指定文档的处理状态。

        解析状态流转只改 documents 表，不读取 MinIO，也不写入 chunk 或 Milvus。
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE documents
                SET status = %s, error_message = %s, updated_at = %s
                WHERE id = %s
                  AND user_id = %s
                  AND knowledge_base_id = %s
                  AND status != 'deleted'
                """,
                (
                    status,
                    error_message,
                    updated_at,
                    document_id,
                    user_id,
                    knowledge_base_id,
                ),
            )
            affected_rows = cursor.rowcount
        await self.connection.commit()

        if affected_rows == 0:
            return None
        return await self.get_by_id_and_knowledge_base(
            user_id,
            knowledge_base_id,
            document_id,
        )

    async def set_task_id_by_id_and_knowledge_base(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        task_id: str,
        updated_at: datetime,
    ) -> Document | None:
        """保存 Celery 解析任务 ID，文档状态保持 uploaded。"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE documents
                SET task_id = %s, updated_at = %s
                WHERE id = %s
                  AND user_id = %s
                  AND knowledge_base_id = %s
                  AND status != 'deleted'
                """,
                (task_id, updated_at, document_id, user_id, knowledge_base_id),
            )
            affected_rows = cursor.rowcount
        await self.connection.commit()

        if affected_rows == 0:
            return None
        return await self.get_by_id_and_knowledge_base(
            user_id,
            knowledge_base_id,
            document_id,
        )

    async def _get_by_id_and_knowledge_base_including_deleted(
        self,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
    ) -> Document | None:
        """查询文档记录本身，用于返回刚刚软删除后的对象。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    knowledge_base_id,
                    file_name,
                    file_type,
                    file_size,
                    storage_bucket,
                    storage_object_key,
                    status,
                    error_message,
                    task_id,
                    created_at,
                    updated_at
                FROM documents
                WHERE id = %s AND user_id = %s AND knowledge_base_id = %s
                LIMIT 1
                """,
                (document_id, user_id, knowledge_base_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._from_row(row)

    @staticmethod
    def _from_row(row: dict[str, object]) -> Document:
        """将 aiomysql DictCursor 返回的行数据转换为内部实体。"""
        return Document(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            knowledge_base_id=str(row["knowledge_base_id"]),
            file_name=str(row["file_name"]),
            file_type=str(row["file_type"]),
            file_size=int(row["file_size"]),
            storage_bucket=str(row["storage_bucket"]),
            storage_object_key=str(row["storage_object_key"]),
            status=str(row["status"]),
            error_message=(
                None if row["error_message"] is None else str(row["error_message"])
            ),
            task_id=None if row["task_id"] is None else str(row["task_id"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
