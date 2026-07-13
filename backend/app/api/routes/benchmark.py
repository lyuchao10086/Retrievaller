import csv
import io
import json
from datetime import datetime, timezone
from typing import Annotated, Literal, Protocol
from uuid import uuid4

import aiomysql
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.models.benchmark import BenchmarkCase
from app.repositories.benchmark import BenchmarkRepository, MySQLBenchmarkRepository
from app.repositories.knowledge_base import KnowledgeBaseRepository, MySQLKnowledgeBaseRepository
from app.repositories.knowledge_base_config import KnowledgeBaseConfigRepository
from app.api.routes.knowledge_base import get_knowledge_base_config_repository
from app.schemas.benchmark import (
    BenchmarkCaseImportRequest,
    BenchmarkCaseImportResponse,
    BenchmarkCaseInput,
    BenchmarkCaseResponse,
    BenchmarkCaseResultResponse,
    BenchmarkRunComparisonResponse,
    BenchmarkRunDetailResponse,
    BenchmarkRunListResponse,
    BenchmarkRunResponse,
)
from app.services.benchmark import (
    BenchmarkCasesRequiredError,
    compare_run_metrics,
    create_benchmark_run,
)
from app.services.knowledge_base_config import get_or_create_knowledge_base_config
from app.tasks.benchmark_evaluation import run_benchmark_task


router = APIRouter(
    prefix="/api/knowledge-bases/{kb_id}",
    tags=["benchmarks"],
    dependencies=[Depends(get_current_user)],
)


class BenchmarkTaskDispatcher(Protocol):
    def delay(self, user_id: str, knowledge_base_id: str, run_id: str): ...


async def get_benchmark_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> BenchmarkRepository:
    return MySQLBenchmarkRepository(connection)


async def get_knowledge_base_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> KnowledgeBaseRepository:
    return MySQLKnowledgeBaseRepository(connection)


def get_benchmark_task_dispatcher() -> BenchmarkTaskDispatcher:
    return run_benchmark_task


async def _require_knowledge_base(
    repository: KnowledgeBaseRepository, kb_id: str, user_id: str
) -> None:
    if await repository.get_active_by_id_and_user(kb_id, user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")


@router.get("/benchmarks", response_model=list[BenchmarkCaseResponse])
async def list_benchmark_cases_api(
    kb_id: str,
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)],
    benchmark_repository: Annotated[BenchmarkRepository, Depends(get_benchmark_repository)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[BenchmarkCaseResponse]:
    await _require_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    return [BenchmarkCaseResponse.model_validate(item) for item in await benchmark_repository.list_cases(kb_id, current_user.id)]


@router.post("/benchmarks/import", response_model=BenchmarkCaseImportResponse)
async def import_benchmark_cases_api(
    kb_id: str,
    payload: BenchmarkCaseImportRequest,
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)],
    benchmark_repository: Annotated[BenchmarkRepository, Depends(get_benchmark_repository)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> BenchmarkCaseImportResponse:
    await _require_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    cases = _build_cases(kb_id, current_user.id, payload.items)
    if payload.mode == "replace":
        saved = await benchmark_repository.replace_cases(current_user.id, kb_id, cases)
    else:
        saved = await benchmark_repository.insert_cases(cases)
    return BenchmarkCaseImportResponse(
        items=[BenchmarkCaseResponse.model_validate(item) for item in saved], mode=payload.mode
    )


@router.post("/benchmarks/import/csv", response_model=BenchmarkCaseImportResponse)
async def import_benchmark_cases_csv_api(
    kb_id: str,
    csv_text: Annotated[str, Body(media_type="text/csv")],
    mode: Annotated[Literal["replace", "append"], Query()] = "replace",
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)] = None,
    benchmark_repository: Annotated[BenchmarkRepository, Depends(get_benchmark_repository)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
) -> BenchmarkCaseImportResponse:
    await _require_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    try:
        items = [BenchmarkCaseInput.model_validate(_csv_row_to_payload(row)) for row in csv.DictReader(io.StringIO(csv_text))]
    except (csv.Error, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid benchmark CSV") from exc
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Benchmark CSV contains no rows")
    cases = _build_cases(kb_id, current_user.id, items)
    saved = (
        await benchmark_repository.replace_cases(current_user.id, kb_id, cases)
        if mode == "replace"
        else await benchmark_repository.insert_cases(cases)
    )
    return BenchmarkCaseImportResponse(
        items=[BenchmarkCaseResponse.model_validate(item) for item in saved], mode=mode
    )


@router.get("/benchmarks/export")
async def export_benchmark_cases_api(
    kb_id: str,
    format: Annotated[Literal["json", "csv"], Query()] = "json",
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)] = None,
    benchmark_repository: Annotated[BenchmarkRepository, Depends(get_benchmark_repository)] = None,
    current_user: Annotated[CurrentUser, Depends(get_current_user)] = None,
) -> Response:
    await _require_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    cases = await benchmark_repository.list_cases(kb_id, current_user.id)
    responses = [BenchmarkCaseResponse.model_validate(item) for item in cases]
    if format == "json":
        return JSONResponse(content=jsonable_encoder({"items": responses}))
    return Response(
        content=_cases_to_csv(responses),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="benchmark-cases.csv"'},
    )


@router.post("/benchmark-runs", response_model=BenchmarkRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_benchmark_run_api(
    kb_id: str,
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)],
    config_repository: Annotated[KnowledgeBaseConfigRepository, Depends(get_knowledge_base_config_repository)],
    benchmark_repository: Annotated[BenchmarkRepository, Depends(get_benchmark_repository)],
    dispatcher: Annotated[BenchmarkTaskDispatcher, Depends(get_benchmark_task_dispatcher)],
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> BenchmarkRunResponse:
    await _require_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    config = await get_or_create_knowledge_base_config(config_repository, kb_id, current_user.id, settings)
    try:
        submission = await create_benchmark_run(
            benchmark_repository,
            knowledge_base_id=kb_id,
            user_id=current_user.id,
            config=config,
            evaluator_model=settings.deepseek_model,
            application_version=settings.app_version,
        )
    except BenchmarkCasesRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if submission.created:
        try:
            task = dispatcher.delay(current_user.id, kb_id, submission.run.id)
        except Exception as exc:
            submission.run.status = "failed"
            submission.run.error_message = "Benchmark task submission failed"
            submission.run.updated_at = _now()
            await benchmark_repository.update_run(submission.run)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Benchmark task queue unavailable") from exc
        submission.run.task_id = str(task.id)
        submission.run.updated_at = _now()
        await benchmark_repository.update_run(submission.run)
    return BenchmarkRunResponse.model_validate(submission.run)


@router.get("/benchmark-runs", response_model=BenchmarkRunListResponse)
async def list_benchmark_runs_api(
    kb_id: str,
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)],
    benchmark_repository: Annotated[BenchmarkRepository, Depends(get_benchmark_repository)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> BenchmarkRunListResponse:
    await _require_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    runs = await benchmark_repository.list_runs(kb_id, current_user.id)
    return BenchmarkRunListResponse(items=[BenchmarkRunResponse.model_validate(run) for run in runs])


@router.get("/benchmark-runs/{run_id}", response_model=BenchmarkRunDetailResponse)
async def get_benchmark_run_api(
    kb_id: str,
    run_id: str,
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)],
    benchmark_repository: Annotated[BenchmarkRepository, Depends(get_benchmark_repository)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> BenchmarkRunDetailResponse:
    await _require_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    run = await benchmark_repository.get_run(run_id, kb_id, current_user.id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark run not found")
    results = await benchmark_repository.list_case_results(run_id, current_user.id)
    return BenchmarkRunDetailResponse(
        run=BenchmarkRunResponse.model_validate(run),
        results=[BenchmarkCaseResultResponse.model_validate(result) for result in results],
    )


@router.get("/benchmark-runs/{baseline_run_id}/compare/{candidate_run_id}", response_model=BenchmarkRunComparisonResponse)
async def compare_benchmark_runs_api(
    kb_id: str,
    baseline_run_id: str,
    candidate_run_id: str,
    knowledge_base_repository: Annotated[KnowledgeBaseRepository, Depends(get_knowledge_base_repository)],
    benchmark_repository: Annotated[BenchmarkRepository, Depends(get_benchmark_repository)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> BenchmarkRunComparisonResponse:
    await _require_knowledge_base(knowledge_base_repository, kb_id, current_user.id)
    baseline = await benchmark_repository.get_run(baseline_run_id, kb_id, current_user.id)
    candidate = await benchmark_repository.get_run(candidate_run_id, kb_id, current_user.id)
    if baseline is None or candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark run not found")
    allowed_statuses = {"completed", "completed_with_errors", "failed"}
    if baseline.status not in allowed_statuses or candidate.status not in allowed_statuses:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Benchmark run is not finished")
    comparison = compare_run_metrics(
        await benchmark_repository.list_case_results(baseline.id, current_user.id),
        await benchmark_repository.list_case_results(candidate.id, current_user.id),
    )
    return BenchmarkRunComparisonResponse(
        baseline_run_id=baseline.id, candidate_run_id=candidate.id, **comparison
    )


def _build_cases(kb_id: str, user_id: str, items: list[BenchmarkCaseInput]) -> list[BenchmarkCase]:
    now = _now()
    return [
        BenchmarkCase(
            id=f"benchmark_case_{uuid4().hex}", user_id=user_id, knowledge_base_id=kb_id,
            question=item.question, expected_answer=item.expected_answer,
            expected_document_ids=item.expected_document_ids, expected_chunk_ids=item.expected_chunk_ids,
            tags=item.tags, enabled=item.enabled, created_at=now, updated_at=now,
        )
        for item in items
    ]


def _csv_row_to_payload(row: dict[str, str | None]) -> dict[str, object]:
    return {
        "question": row.get("question") or "",
        "expected_answer": row.get("expected_answer") or None,
        "expected_document_ids": _csv_json_list(row.get("expected_document_ids")),
        "expected_chunk_ids": _csv_json_list(row.get("expected_chunk_ids")),
        "tags": _csv_json_list(row.get("tags")),
        "enabled": str(row.get("enabled") or "true").strip().lower() not in {"false", "0", "no"},
    }


def _csv_json_list(value: str | None) -> list[str]:
    parsed = json.loads(value or "[]")
    if not isinstance(parsed, list):
        raise ValueError("Expected JSON array")
    return [str(item) for item in parsed]


def _cases_to_csv(cases: list[BenchmarkCaseResponse]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["question", "expected_answer", "expected_document_ids", "expected_chunk_ids", "tags", "enabled"])
    writer.writeheader()
    for case in cases:
        writer.writerow({
            "question": case.question, "expected_answer": case.expected_answer or "",
            "expected_document_ids": json.dumps(case.expected_document_ids, ensure_ascii=False),
            "expected_chunk_ids": json.dumps(case.expected_chunk_ids, ensure_ascii=False),
            "tags": json.dumps(case.tags, ensure_ascii=False), "enabled": str(case.enabled).lower(),
        })
    return output.getvalue()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
