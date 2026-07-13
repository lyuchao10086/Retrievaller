import json
from datetime import datetime
from typing import Any, Protocol

import aiomysql

from app.models.benchmark import BenchmarkCase, BenchmarkCaseResult, BenchmarkRun


class BenchmarkRepository(Protocol):
    async def replace_cases(self, user_id: str, knowledge_base_id: str, cases: list[BenchmarkCase]) -> list[BenchmarkCase]: ...
    async def insert_cases(self, cases: list[BenchmarkCase]) -> list[BenchmarkCase]: ...
    async def list_cases(self, knowledge_base_id: str, user_id: str) -> list[BenchmarkCase]: ...
    async def list_enabled_cases(self, knowledge_base_id: str, user_id: str) -> list[BenchmarkCase]: ...
    async def get_active_run(self, knowledge_base_id: str, user_id: str) -> BenchmarkRun | None: ...
    async def insert_run(self, run: BenchmarkRun) -> BenchmarkRun: ...
    async def update_run(self, run: BenchmarkRun) -> BenchmarkRun: ...
    async def get_run(self, run_id: str, knowledge_base_id: str, user_id: str) -> BenchmarkRun | None: ...
    async def list_runs(self, knowledge_base_id: str, user_id: str, limit: int = 50) -> list[BenchmarkRun]: ...
    async def insert_case_result(self, result: BenchmarkCaseResult) -> BenchmarkCaseResult: ...
    async def list_case_results(self, run_id: str, user_id: str) -> list[BenchmarkCaseResult]: ...


class MySQLBenchmarkRepository:
    def __init__(self, connection: aiomysql.Connection):
        self.connection = connection

    async def replace_cases(self, user_id: str, knowledge_base_id: str, cases: list[BenchmarkCase]) -> list[BenchmarkCase]:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                "UPDATE benchmark_cases SET enabled = FALSE WHERE user_id = %s AND knowledge_base_id = %s",
                (user_id, knowledge_base_id),
            )
            await self._insert_cases(cursor, cases)
        await self.connection.commit()
        return cases

    async def insert_cases(self, cases: list[BenchmarkCase]) -> list[BenchmarkCase]:
        if not cases:
            return []
        async with self.connection.cursor() as cursor:
            await self._insert_cases(cursor, cases)
        await self.connection.commit()
        return cases

    async def list_cases(self, knowledge_base_id: str, user_id: str) -> list[BenchmarkCase]:
        return await self._list_cases(knowledge_base_id, user_id, enabled_only=False)

    async def list_enabled_cases(self, knowledge_base_id: str, user_id: str) -> list[BenchmarkCase]:
        return await self._list_cases(knowledge_base_id, user_id, enabled_only=True)

    async def get_active_run(self, knowledge_base_id: str, user_id: str) -> BenchmarkRun | None:
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT * FROM benchmark_runs
                WHERE knowledge_base_id = %s AND user_id = %s
                  AND status IN ('queued', 'running')
                ORDER BY created_at DESC LIMIT 1
                """,
                (knowledge_base_id, user_id),
            )
            row = await cursor.fetchone()
        return None if row is None else self._run_from_row(row)

    async def insert_run(self, run: BenchmarkRun) -> BenchmarkRun:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO benchmark_runs (
                    id, user_id, knowledge_base_id, task_id, status, config_snapshot_json,
                    case_snapshot_json, case_count, metrics_json, error_message, started_at, completed_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                self._run_values(run),
            )
        await self.connection.commit()
        return run

    async def update_run(self, run: BenchmarkRun) -> BenchmarkRun:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE benchmark_runs
                SET task_id = %s, status = %s, config_snapshot_json = %s, case_snapshot_json = %s, case_count = %s,
                    metrics_json = %s, error_message = %s, started_at = %s, completed_at = %s,
                    updated_at = %s
                WHERE id = %s AND user_id = %s AND knowledge_base_id = %s
                """,
                (
                    run.task_id, run.status, _dump(run.config_snapshot), _dump(run.case_snapshot), run.case_count,
                    _dump(run.metrics) if run.metrics is not None else None, run.error_message,
                    run.started_at, run.completed_at, run.updated_at,
                    run.id, run.user_id, run.knowledge_base_id,
                ),
            )
            if cursor.rowcount == 0:
                raise LookupError("Benchmark run not found")
        await self.connection.commit()
        return run

    async def get_run(self, run_id: str, knowledge_base_id: str, user_id: str) -> BenchmarkRun | None:
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT * FROM benchmark_runs WHERE id = %s AND knowledge_base_id = %s AND user_id = %s LIMIT 1",
                (run_id, knowledge_base_id, user_id),
            )
            row = await cursor.fetchone()
        return None if row is None else self._run_from_row(row)

    async def list_runs(self, knowledge_base_id: str, user_id: str, limit: int = 50) -> list[BenchmarkRun]:
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT * FROM benchmark_runs WHERE knowledge_base_id = %s AND user_id = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (knowledge_base_id, user_id, limit),
            )
            rows = await cursor.fetchall()
        return [self._run_from_row(row) for row in rows]

    async def insert_case_result(self, result: BenchmarkCaseResult) -> BenchmarkCaseResult:
        async with self.connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO benchmark_case_results (
                    id, run_id, benchmark_case_id, question, expected_answer,
                    expected_document_ids_json, expected_chunk_ids_json, tags_json, answer, sources_json,
                    returned_document_ids_json, returned_chunk_ids_json, retrieval_document_hit,
                    retrieval_chunk_hit, citation_hit, faithfulness_score, relevance_score, citation_score,
                    completeness_score, hallucination, overall_score, evaluation_reason, duration_ms,
                    status, error_message, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                self._result_values(result),
            )
        await self.connection.commit()
        return result

    async def list_case_results(self, run_id: str, user_id: str) -> list[BenchmarkCaseResult]:
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT results.* FROM benchmark_case_results AS results
                INNER JOIN benchmark_runs AS runs ON runs.id = results.run_id
                WHERE results.run_id = %s AND runs.user_id = %s
                ORDER BY results.created_at ASC
                """,
                (run_id, user_id),
            )
            rows = await cursor.fetchall()
        return [self._result_from_row(row) for row in rows]

    async def _list_cases(self, knowledge_base_id: str, user_id: str, *, enabled_only: bool) -> list[BenchmarkCase]:
        condition = " AND enabled = TRUE" if enabled_only else ""
        async with self.connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                f"""
                SELECT * FROM benchmark_cases
                WHERE knowledge_base_id = %s AND user_id = %s{condition}
                ORDER BY created_at ASC
                """,
                (knowledge_base_id, user_id),
            )
            rows = await cursor.fetchall()
        return [self._case_from_row(row) for row in rows]

    @staticmethod
    async def _insert_cases(cursor: aiomysql.Cursor, cases: list[BenchmarkCase]) -> None:
        if not cases:
            return
        await cursor.executemany(
            """
            INSERT INTO benchmark_cases (
                id, user_id, knowledge_base_id, question, expected_answer,
                expected_document_ids_json, expected_chunk_ids_json, tags_json, enabled, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    case.id, case.user_id, case.knowledge_base_id, case.question, case.expected_answer,
                    _dump(case.expected_document_ids), _dump(case.expected_chunk_ids), _dump(case.tags),
                    case.enabled, case.created_at, case.updated_at,
                )
                for case in cases
            ],
        )

    @staticmethod
    def _run_values(run: BenchmarkRun) -> tuple[object, ...]:
        return (
            run.id, run.user_id, run.knowledge_base_id, run.task_id, run.status,
            _dump(run.config_snapshot), _dump(run.case_snapshot), run.case_count,
            _dump(run.metrics) if run.metrics is not None else None, run.error_message,
            run.started_at, run.completed_at, run.created_at, run.updated_at,
        )

    @staticmethod
    def _result_values(result: BenchmarkCaseResult) -> tuple[object, ...]:
        return (
            result.id, result.run_id, result.benchmark_case_id, result.question, result.expected_answer,
            _dump(result.expected_document_ids), _dump(result.expected_chunk_ids), _dump(result.tags),
            result.answer, _dump(result.sources_json), _dump(result.returned_document_ids),
            _dump(result.returned_chunk_ids), result.retrieval_document_hit, result.retrieval_chunk_hit,
            result.citation_hit, result.faithfulness_score, result.relevance_score, result.citation_score,
            result.completeness_score, result.hallucination, result.overall_score, result.evaluation_reason,
            result.duration_ms, result.status, result.error_message, result.created_at, result.updated_at,
        )

    @staticmethod
    def _case_from_row(row: dict[str, object]) -> BenchmarkCase:
        return BenchmarkCase(
            id=str(row["id"]), user_id=str(row["user_id"]), knowledge_base_id=str(row["knowledge_base_id"]),
            question=str(row["question"]), expected_answer=_optional_str(row["expected_answer"]),
            expected_document_ids=_json_list(row["expected_document_ids_json"]),
            expected_chunk_ids=_json_list(row["expected_chunk_ids_json"]), tags=_json_list(row["tags_json"]),
            enabled=bool(row["enabled"]), created_at=_datetime(row["created_at"]), updated_at=_datetime(row["updated_at"]),
        )

    @staticmethod
    def _run_from_row(row: dict[str, object]) -> BenchmarkRun:
        return BenchmarkRun(
            id=str(row["id"]), user_id=str(row["user_id"]), knowledge_base_id=str(row["knowledge_base_id"]),
            task_id=_optional_str(row["task_id"]), status=str(row["status"]),
            config_snapshot=_json_dict(row["config_snapshot_json"]), case_count=int(row["case_count"]),
            case_snapshot=_json_dict_list(row.get("case_snapshot_json")),
            metrics=_json_dict(row["metrics_json"]) if row["metrics_json"] is not None else None,
            error_message=_optional_str(row["error_message"]), started_at=_optional_datetime(row["started_at"]),
            completed_at=_optional_datetime(row["completed_at"]), created_at=_datetime(row["created_at"]),
            updated_at=_datetime(row["updated_at"]),
        )

    @staticmethod
    def _result_from_row(row: dict[str, object]) -> BenchmarkCaseResult:
        return BenchmarkCaseResult(
            id=str(row["id"]), run_id=str(row["run_id"]), benchmark_case_id=str(row["benchmark_case_id"]),
            question=str(row["question"]), expected_answer=_optional_str(row["expected_answer"]),
            expected_document_ids=_json_list(row["expected_document_ids_json"]),
            expected_chunk_ids=_json_list(row["expected_chunk_ids_json"]), tags=_json_list(row["tags_json"]),
            answer=_optional_str(row["answer"]), sources_json=_json_dict_list(row["sources_json"]),
            returned_document_ids=_json_list(row["returned_document_ids_json"]),
            returned_chunk_ids=_json_list(row["returned_chunk_ids_json"]),
            retrieval_document_hit=_optional_bool(row["retrieval_document_hit"]),
            retrieval_chunk_hit=_optional_bool(row["retrieval_chunk_hit"]), citation_hit=_optional_bool(row["citation_hit"]),
            faithfulness_score=_optional_int(row["faithfulness_score"]), relevance_score=_optional_int(row["relevance_score"]),
            citation_score=_optional_int(row["citation_score"]), completeness_score=_optional_int(row["completeness_score"]),
            hallucination=_optional_bool(row["hallucination"]), overall_score=_optional_int(row["overall_score"]),
            evaluation_reason=_optional_str(row["evaluation_reason"]), duration_ms=int(row["duration_ms"]),
            status=str(row["status"]), error_message=_optional_str(row["error_message"]),
            created_at=_datetime(row["created_at"]), updated_at=_datetime(row["updated_at"]),
        )


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_dict(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_dict_list(value: object) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("Expected datetime value from MySQL")
    return value


def _optional_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_bool(value: object) -> bool | None:
    return None if value is None else bool(value)
