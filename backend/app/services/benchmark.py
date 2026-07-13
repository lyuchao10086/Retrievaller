from collections.abc import Iterable
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean
from typing import Any
from uuid import uuid4

from app.models.benchmark import BenchmarkCase, BenchmarkCaseResult, BenchmarkRun
from app.models.knowledge_base_config import KnowledgeBaseConfig


_AVERAGE_SCORE_KEYS = (
    "overall_score",
    "faithfulness_score",
    "relevance_score",
    "citation_score",
    "completeness_score",
)


class BenchmarkCasesRequiredError(ValueError):
    """A run cannot be created without at least one enabled case."""


class BenchmarkRunSubmission:
    def __init__(self, run: BenchmarkRun, created: bool):
        self.run = run
        self.created = created


async def create_benchmark_run(
    repository: Any,
    *,
    knowledge_base_id: str,
    user_id: str,
    config: KnowledgeBaseConfig,
    evaluator_model: str,
    application_version: str,
) -> BenchmarkRunSubmission:
    """Create one queued run or return the existing in-progress run idempotently."""
    active = await repository.get_active_run(knowledge_base_id, user_id)
    if active is not None:
        return BenchmarkRunSubmission(active, created=False)
    cases = await repository.list_enabled_cases(knowledge_base_id, user_id)
    if not cases:
        raise BenchmarkCasesRequiredError("At least one enabled benchmark case is required")
    now = _now()
    run = BenchmarkRun(
        id=f"benchmark_run_{uuid4().hex}",
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        task_id=None,
        status="queued",
        config_snapshot=build_config_snapshot(config, evaluator_model, application_version),
        case_snapshot=[_case_snapshot(case) for case in cases],
        case_count=len(cases),
        metrics=None,
        error_message=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    return BenchmarkRunSubmission(await repository.insert_run(run), created=True)


def benchmark_cases_from_snapshot(run: BenchmarkRun) -> list[BenchmarkCase]:
    """Recreate the immutable input set rather than querying a later-edited dataset."""
    cases: list[BenchmarkCase] = []
    for item in run.case_snapshot:
        if not isinstance(item, dict):
            continue
        try:
            cases.append(
                BenchmarkCase(
                    id=str(item["id"]), user_id=run.user_id, knowledge_base_id=run.knowledge_base_id,
                    question=str(item["question"]), expected_answer=_optional_text(item.get("expected_answer")),
                    expected_document_ids=_string_list(item.get("expected_document_ids")),
                    expected_chunk_ids=_string_list(item.get("expected_chunk_ids")),
                    tags=_string_list(item.get("tags")), enabled=True,
                    created_at=run.created_at, updated_at=run.created_at,
                )
            )
        except KeyError:
            continue
    return cases


def build_config_snapshot(
    config: KnowledgeBaseConfig,
    evaluator_model: str,
    application_version: str,
) -> dict[str, object]:
    """Store the values actually used by a run, not a mutable config reference."""
    return {
        "config_version": config.version,
        "processing": deepcopy(config.processing_dict()),
        "retrieval": deepcopy(config.retrieval_dict()),
        "generation": deepcopy(config.generation_dict()),
        "models": {
            "embedding": config.processing.embedding_model_name,
            "rerank": config.retrieval.rerank_model_name,
            "llm": config.generation.llm_model_name,
            "evaluator": evaluator_model,
        },
        "application_version": application_version,
    }


def resolve_source_hits(result: BenchmarkCaseResult) -> tuple[bool | None, bool | None, bool | None]:
    """Calculate only the retrieval metrics whose expected targets are known."""
    expected_documents = set(result.expected_document_ids)
    expected_chunks = set(result.expected_chunk_ids)
    returned_documents = set(result.returned_document_ids)
    returned_chunks = set(result.returned_chunk_ids)

    document_hit = bool(expected_documents & returned_documents) if expected_documents else None
    chunk_hit = bool(expected_chunks & returned_chunks) if expected_chunks else None
    citation_hit = (
        bool((expected_documents & returned_documents) or (expected_chunks & returned_chunks))
        if expected_documents or expected_chunks
        else None
    )
    return document_hit, chunk_hit, citation_hit


def build_run_metrics(results: Iterable[BenchmarkCaseResult]) -> dict[str, Any]:
    """Produce reproducible aggregates without turning absent expectations into misses."""
    items = list(results)
    completed = [item for item in items if item.status == "completed"]
    failed = [item for item in items if item.status == "failed"]
    document_hits: list[bool] = []
    chunk_hits: list[bool] = []
    citation_hits: list[bool] = []
    for result in items:
        document_hit, chunk_hit, citation_hit = resolve_source_hits(result)
        if document_hit is not None:
            document_hits.append(document_hit)
        if chunk_hit is not None:
            chunk_hits.append(chunk_hit)
        if citation_hit is not None:
            citation_hits.append(citation_hit)

    metrics: dict[str, Any] = {
        "case_count": len(items),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "success_rate": len(completed) / len(items) if items else 0.0,
        "average_duration_ms": mean(item.duration_ms for item in items) if items else 0.0,
        "document_hit_rate": _hit_rate(document_hits),
        "document_hit_case_count": len(document_hits),
        "chunk_hit_rate": _hit_rate(chunk_hits),
        "chunk_hit_case_count": len(chunk_hits),
        "citation_hit_rate": _hit_rate(citation_hits),
        "citation_hit_case_count": len(citation_hits),
    }
    evaluated = [item for item in completed if item.overall_score is not None]
    for key in _AVERAGE_SCORE_KEYS:
        values = [getattr(item, key) for item in evaluated if getattr(item, key) is not None]
        metrics[f"average_{key}"] = mean(values) if values else None
    metrics["evaluated_case_count"] = len(evaluated)
    return metrics


def compare_run_metrics(
    baseline_results: Iterable[BenchmarkCaseResult],
    candidate_results: Iterable[BenchmarkCaseResult],
) -> dict[str, Any]:
    """Compare persisted results; no retrieval or model invocation occurs here."""
    baseline_items = list(baseline_results)
    candidate_items = list(candidate_results)
    baseline_metrics = build_run_metrics(baseline_items)
    candidate_metrics = build_run_metrics(candidate_items)
    metric_deltas = {
        key: _metric_delta(baseline_metrics.get(key), candidate_metrics.get(key))
        for key in baseline_metrics
        if key in candidate_metrics
        and (key.endswith("_rate") or key.startswith("average_") or key == "success_rate")
    }
    baseline_by_case = {item.benchmark_case_id: item for item in baseline_items}
    candidate_by_case = {item.benchmark_case_id: item for item in candidate_items}
    degraded = [
        case_id
        for case_id in baseline_by_case.keys() & candidate_by_case.keys()
        if _is_degraded(baseline_by_case[case_id], candidate_by_case[case_id])
    ]
    return {
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "metric_deltas": metric_deltas,
        "degraded_case_ids": sorted(degraded),
    }


async def execute_benchmark_run_cases(
    repository: Any,
    run: BenchmarkRun,
    cases: Iterable[BenchmarkCase],
    answer_case: Callable[[str, dict[str, object]], Awaitable[tuple[str, list[dict[str, Any]]]]],
    evaluate_answer: Callable[[str, str, list[dict[str, Any]]], Awaitable[dict[str, Any]]],
) -> BenchmarkRun:
    """Run frozen cases sequentially and isolate a single case failure from the run."""
    now = _now()
    run.status = "running"
    run.started_at = now
    run.updated_at = now
    await repository.update_run(run)
    results: list[BenchmarkCaseResult] = []
    snapshot = deepcopy(run.config_snapshot)
    for case in cases:
        started_at = datetime.now(timezone.utc)
        try:
            answer, sources = await answer_case(case.question, deepcopy(snapshot))
            returned_document_ids, returned_chunk_ids = _source_ids(sources)
        except Exception as exc:
            result = _build_case_result(
                run,
                case,
                answer=None,
                sources=[],
                returned_document_ids=[],
                returned_chunk_ids=[],
                scores={},
                duration_ms=_duration_ms(started_at),
                status="failed",
                error_message=_safe_case_error(exc),
            )
        else:
            try:
                scores = await evaluate_answer(case.question, answer, sources)
            except Exception as exc:
                result = _build_case_result(
                    run,
                    case,
                    answer=answer,
                    sources=sources,
                    returned_document_ids=returned_document_ids,
                    returned_chunk_ids=returned_chunk_ids,
                    scores={},
                    duration_ms=_duration_ms(started_at),
                    status="failed",
                    error_message=_safe_case_error(exc),
                )
            else:
                result = _build_case_result(
                    run,
                    case,
                    answer=answer,
                    sources=sources,
                    returned_document_ids=returned_document_ids,
                    returned_chunk_ids=returned_chunk_ids,
                    scores=scores,
                    duration_ms=_duration_ms(started_at),
                    status="completed",
                    error_message=None,
                )
        await repository.insert_case_result(result)
        results.append(result)

    run.metrics = build_run_metrics(results)
    completed_count = int(run.metrics["completed_count"])
    run.status = (
        "completed"
        if completed_count == len(results)
        else "completed_with_errors"
        if completed_count
        else "failed"
    )
    run.completed_at = _now()
    run.updated_at = run.completed_at
    run.error_message = (
        "One or more benchmark cases failed" if run.status == "completed_with_errors" else None
    )
    await repository.update_run(run)
    return run


def _hit_rate(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _metric_delta(baseline: object, candidate: object) -> float | None:
    if baseline is None or candidate is None:
        return None
    return float(candidate) - float(baseline)


def _is_degraded(baseline: BenchmarkCaseResult, candidate: BenchmarkCaseResult) -> bool:
    if baseline.status == "completed" and candidate.status != "completed":
        return True
    baseline_document_hit, baseline_chunk_hit, baseline_citation_hit = resolve_source_hits(baseline)
    candidate_document_hit, candidate_chunk_hit, candidate_citation_hit = resolve_source_hits(candidate)
    if baseline_document_hit is True and candidate_document_hit is False:
        return True
    if baseline_chunk_hit is True and candidate_chunk_hit is False:
        return True
    if baseline_citation_hit is True and candidate_citation_hit is False:
        return True
    return (
        baseline.overall_score is not None
        and candidate.overall_score is not None
        and candidate.overall_score < baseline.overall_score
    )


def _build_case_result(
    run: BenchmarkRun,
    case: BenchmarkCase,
    *,
    answer: str | None,
    sources: list[dict[str, Any]],
    returned_document_ids: list[str],
    returned_chunk_ids: list[str],
    scores: dict[str, Any],
    duration_ms: int,
    status: str,
    error_message: str | None,
) -> BenchmarkCaseResult:
    now = _now()
    result = BenchmarkCaseResult(
        id=f"benchmark_result_{uuid4().hex}",
        run_id=run.id,
        benchmark_case_id=case.id,
        question=case.question,
        expected_answer=case.expected_answer,
        expected_document_ids=list(case.expected_document_ids),
        expected_chunk_ids=list(case.expected_chunk_ids),
        tags=list(case.tags),
        answer=answer,
        sources_json=sources,
        returned_document_ids=returned_document_ids,
        returned_chunk_ids=returned_chunk_ids,
        retrieval_document_hit=None,
        retrieval_chunk_hit=None,
        citation_hit=None,
        faithfulness_score=_optional_score(scores.get("faithfulness_score")),
        relevance_score=_optional_score(scores.get("relevance_score")),
        citation_score=_optional_score(scores.get("citation_score")),
        completeness_score=_optional_score(scores.get("completeness_score")),
        hallucination=scores.get("hallucination") if isinstance(scores.get("hallucination"), bool) else None,
        overall_score=_optional_score(scores.get("overall_score")),
        evaluation_reason=_optional_text(scores.get("reason")),
        duration_ms=duration_ms,
        status=status,
        error_message=error_message,
        created_at=now,
        updated_at=now,
    )
    (
        result.retrieval_document_hit,
        result.retrieval_chunk_hit,
        result.citation_hit,
    ) = resolve_source_hits(result)
    return result


def _source_ids(sources: Iterable[dict[str, Any]]) -> tuple[list[str], list[str]]:
    document_ids: list[str] = []
    chunk_ids: list[str] = []
    for source in sources:
        document_id = source.get("document_id")
        chunk_id = source.get("chunk_id")
        if isinstance(document_id, str) and document_id and document_id not in document_ids:
            document_ids.append(document_id)
        if isinstance(chunk_id, str) and chunk_id and chunk_id not in chunk_ids:
            chunk_ids.append(chunk_id)
    return document_ids, chunk_ids


def _optional_score(value: object) -> int | None:
    return value if isinstance(value, int) and 1 <= value <= 5 else None


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _duration_ms(started_at: datetime) -> int:
    return max(0, round((datetime.now(timezone.utc) - started_at).total_seconds() * 1000))


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _case_snapshot(case: BenchmarkCase) -> dict[str, Any]:
    return {
        "id": case.id, "question": case.question, "expected_answer": case.expected_answer,
        "expected_document_ids": list(case.expected_document_ids),
        "expected_chunk_ids": list(case.expected_chunk_ids), "tags": list(case.tags),
    }


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _safe_case_error(exc: Exception) -> str:
    """Expose a stable operational category without leaking provider response bodies."""
    categories = {
        "DeepSeekConfigurationError": "Answer evaluator is not configured",
        "DeepSeekAPIError": "Answer evaluator is unavailable",
        "DeepSeekInvalidJSONError": "Answer evaluator returned an invalid result",
        "LocalLLMUnavailableError": "LLM service is unavailable",
        "RerankUnavailableError": "Rerank service is unavailable",
    }
    return categories.get(type(exc).__name__, "Benchmark case execution failed")
