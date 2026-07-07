import json
from typing import Any, Protocol

import aiomysql

from app.models.qa_record import QaRecord


class QaRecordRepository(Protocol):
    """问答记录 service 层依赖的数据存储接口约定。"""

    async def insert(self, record: QaRecord) -> QaRecord:
        raise NotImplementedError

    async def list_recent_by_user(self, user_id: str, limit: int = 50) -> list[QaRecord]:
        raise NotImplementedError

    async def get_by_id_and_user(
        self,
        qa_record_id: str,
        user_id: str,
    ) -> QaRecord | None:
        raise NotImplementedError

    async def delete_by_id_and_user(
        self,
        qa_record_id: str,
        user_id: str,
    ) -> QaRecord | None:
        raise NotImplementedError


class MySQLQaRecordRepository:
    """问答记录持久化的 MySQL 实现。"""

    def __init__(self, connection: aiomysql.Connection):
        self.connection = connection

    async def insert(self, record: QaRecord) -> QaRecord:
        """保存一条成功 RAG 问答记录。"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO qa_records (
                    id,
                    user_id,
                    title,
                    question,
                    answer,
                    knowledge_base_ids,
                    sources_json,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.id,
                    record.user_id,
                    record.title,
                    record.question,
                    record.answer,
                    json.dumps(record.knowledge_base_ids, ensure_ascii=False),
                    json.dumps(record.sources_json, ensure_ascii=False),
                    record.created_at,
                    record.updated_at,
                ),
            )
        await self.connection.commit()
        return record

    async def list_recent_by_user(self, user_id: str, limit: int = 50) -> list[QaRecord]:
        """查询当前用户最近的问答记录。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    title,
                    question,
                    answer,
                    knowledge_base_ids,
                    sources_json,
                    created_at,
                    updated_at
                FROM qa_records
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    async def get_by_id_and_user(
        self,
        qa_record_id: str,
        user_id: str,
    ) -> QaRecord | None:
        """按 qa_record_id 和 user_id 查询单条问答记录。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    title,
                    question,
                    answer,
                    knowledge_base_ids,
                    sources_json,
                    created_at,
                    updated_at
                FROM qa_records
                WHERE id = %s AND user_id = %s
                LIMIT 1
                """,
                (qa_record_id, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._from_row(row)

    async def delete_by_id_and_user(
        self,
        qa_record_id: str,
        user_id: str,
    ) -> QaRecord | None:
        """硬删除当前用户的问答记录，并先清理对应评估结果。"""
        record = await self.get_by_id_and_user(qa_record_id, user_id)
        if record is None:
            return None

        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                DELETE FROM evaluations
                WHERE qa_record_id = %s
                  AND user_id = %s
                """,
                (qa_record_id, user_id),
            )
            await cursor.execute(
                """
                DELETE FROM qa_records
                WHERE id = %s
                  AND user_id = %s
                """,
                (qa_record_id, user_id),
            )
            affected_rows = cursor.rowcount
        await self.connection.commit()

        if affected_rows == 0:
            return None
        return record

    @staticmethod
    def _from_row(row: dict[str, object]) -> QaRecord:
        """将 MySQL 行数据转换为内部实体。"""
        return QaRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            title=str(row.get("title") or _fallback_title(str(row["question"]))),
            question=str(row["question"]),
            answer=str(row["answer"]),
            knowledge_base_ids=_loads_json_list(row["knowledge_base_ids"]),
            sources_json=_loads_json_dict_list(row["sources_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _loads_json_list(value: object) -> list[str]:
    data = json.loads(str(value or "[]"))
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def _loads_json_dict_list(value: object) -> list[dict[str, Any]]:
    data = json.loads(str(value or "[]"))
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _fallback_title(question: str) -> str:
    title = " ".join(question.strip().split())
    return title[:24] if title else "新对话"
