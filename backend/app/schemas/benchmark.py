from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BenchmarkCaseInput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    expected_answer: str | None = Field(default=None, max_length=20000)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        return value


class BenchmarkCaseImportRequest(BaseModel):
    items: list[BenchmarkCaseInput] = Field(min_length=1, max_length=1000)
    mode: Literal["replace", "append"] = "replace"


class BenchmarkCaseResponse(BenchmarkCaseInput):
    id: str
    knowledge_base_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BenchmarkCaseImportResponse(BaseModel):
    items: list[BenchmarkCaseResponse]
    mode: Literal["replace", "append"]


class BenchmarkRunResponse(BaseModel):
    id: str
    knowledge_base_id: str
    task_id: str | None
    status: Literal["queued", "running", "completed", "completed_with_errors", "failed"]
    config_snapshot: dict[str, Any]
    case_count: int
    metrics: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BenchmarkCaseResultResponse(BaseModel):
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
    status: Literal["completed", "failed"]
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BenchmarkRunDetailResponse(BaseModel):
    run: BenchmarkRunResponse
    results: list[BenchmarkCaseResultResponse]


class BenchmarkRunListResponse(BaseModel):
    items: list[BenchmarkRunResponse]


class BenchmarkRunComparisonResponse(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    baseline_metrics: dict[str, Any]
    candidate_metrics: dict[str, Any]
    metric_deltas: dict[str, float | None]
    degraded_case_ids: list[str]
