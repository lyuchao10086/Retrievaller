from typing import Protocol

import aiomysql

from app.models.evaluation import Evaluation


class EvaluationRepository(Protocol):
    """评估 service 层依赖的数据存储接口约定。"""

    async def insert(self, evaluation: Evaluation) -> Evaluation:
        raise NotImplementedError

    async def get_by_qa_record_id_and_user(
        self,
        qa_record_id: str,
        user_id: str,
    ) -> Evaluation | None:
        raise NotImplementedError

    async def list_recent_by_user(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[Evaluation]:
        raise NotImplementedError


class MySQLEvaluationRepository:
    """评估记录持久化的 MySQL 实现。"""

    def __init__(self, connection: aiomysql.Connection):
        self.connection = connection

    async def insert(self, evaluation: Evaluation) -> Evaluation:
        """保存一条 DeepSeek 评估结果。"""
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO evaluations (
                    id,
                    user_id,
                    qa_record_id,
                    faithfulness_score,
                    relevance_score,
                    citation_score,
                    completeness_score,
                    hallucination,
                    overall_score,
                    reason,
                    raw_response,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    evaluation.id,
                    evaluation.user_id,
                    evaluation.qa_record_id,
                    evaluation.faithfulness_score,
                    evaluation.relevance_score,
                    evaluation.citation_score,
                    evaluation.completeness_score,
                    evaluation.hallucination,
                    evaluation.overall_score,
                    evaluation.reason,
                    evaluation.raw_response,
                    evaluation.created_at,
                    evaluation.updated_at,
                ),
            )
        await self.connection.commit()
        return evaluation

    async def get_by_qa_record_id_and_user(
        self,
        qa_record_id: str,
        user_id: str,
    ) -> Evaluation | None:
        """查询当前用户某条问答记录的评估结果。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    qa_record_id,
                    faithfulness_score,
                    relevance_score,
                    citation_score,
                    completeness_score,
                    hallucination,
                    overall_score,
                    reason,
                    raw_response,
                    created_at,
                    updated_at
                FROM evaluations
                WHERE qa_record_id = %s AND user_id = %s
                LIMIT 1
                """,
                (qa_record_id, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._from_row(row)

    async def list_recent_by_user(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[Evaluation]:
        """查询当前用户最近 50 条评估记录。"""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    qa_record_id,
                    faithfulness_score,
                    relevance_score,
                    citation_score,
                    completeness_score,
                    hallucination,
                    overall_score,
                    reason,
                    raw_response,
                    created_at,
                    updated_at
                FROM evaluations
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: dict[str, object]) -> Evaluation:
        """将 MySQL 行数据转换为内部实体。"""
        return Evaluation(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            qa_record_id=str(row["qa_record_id"]),
            faithfulness_score=int(row["faithfulness_score"]),
            relevance_score=int(row["relevance_score"]),
            citation_score=int(row["citation_score"]),
            completeness_score=int(row["completeness_score"]),
            hallucination=bool(row["hallucination"]),
            overall_score=int(row["overall_score"]),
            reason=str(row["reason"]),
            raw_response=str(row["raw_response"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
