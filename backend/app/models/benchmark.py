from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class BenchmarkCase:
    """One user-owned regression question for a knowledge base."""

    id: str
    user_id: str
    knowledge_base_id: str
    question: str
    expected_answer: str | None
    expected_document_ids: list[str]
    expected_chunk_ids: list[str]
    tags: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class BenchmarkRun:
    """An immutable, asynchronous execution of the enabled benchmark cases."""

    id: str
    user_id: str
    knowledge_base_id: str
    task_id: str | None
    status: str
    config_snapshot: dict[str, Any]
    case_snapshot: list[dict[str, Any]]
    case_count: int
    metrics: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class BenchmarkCaseResult:
    """A frozen per-case outcome belonging to one benchmark run."""

    id: str
    run_id: str
    benchmark_case_id: str
    question: str
    expected_answer: str | None
    expected_document_ids: list[str]
    expected_chunk_ids: list[str]
    tags: list[str]
    answer: str | None
    sources_json: list[dict[str, Any]]
    returned_document_ids: list[str]
    returned_chunk_ids: list[str]
    retrieval_document_hit: bool | None
    retrieval_chunk_hit: bool | None
    citation_hit: bool | None
    faithfulness_score: int | None
    relevance_score: int | None
    citation_score: int | None
    completeness_score: int | None
    hallucination: bool | None
    overall_score: int | None
    evaluation_reason: str | None
    duration_ms: int
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime
