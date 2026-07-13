from datetime import datetime, timezone

import asyncio
from copy import deepcopy

from fastapi.testclient import TestClient

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.api.routes.benchmark import (
    get_benchmark_repository,
    get_benchmark_task_dispatcher,
    get_knowledge_base_repository as get_benchmark_knowledge_base_repository,
)
from app.main import app
from app.models.benchmark import BenchmarkCase, BenchmarkCaseResult, BenchmarkRun
from app.models.knowledge_base import KnowledgeBase
from app.services.deepseek_service import DeepSeekConfigurationError
from app.models.knowledge_base_config import (
    GenerationConfig,
    KnowledgeBaseConfig,
    ProcessingConfig,
    RetrievalConfig,
)
from app.services.benchmark import (
    benchmark_cases_from_snapshot,
    build_run_metrics,
    compare_run_metrics,
    create_benchmark_run,
    execute_benchmark_run_cases,
)


def make_result(
    case_id: str,
    *,
    status: str = "completed",
    expected_document_ids: tuple[str, ...] = (),
    expected_chunk_ids: tuple[str, ...] = (),
    returned_document_ids: tuple[str, ...] = (),
    returned_chunk_ids: tuple[str, ...] = (),
    overall_score: int | None = None,
    duration_ms: int = 0,
) -> BenchmarkCaseResult:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return BenchmarkCaseResult(
        id=f"result_{case_id}",
        run_id="run_target",
        benchmark_case_id=case_id,
        question="问题",
        expected_answer=None,
        expected_document_ids=list(expected_document_ids),
        expected_chunk_ids=list(expected_chunk_ids),
        tags=[],
        answer="回答" if status == "completed" else None,
        sources_json=[],
        returned_document_ids=list(returned_document_ids),
        returned_chunk_ids=list(returned_chunk_ids),
        retrieval_document_hit=None,
        retrieval_chunk_hit=None,
        citation_hit=None,
        faithfulness_score=overall_score,
        relevance_score=overall_score,
        citation_score=overall_score,
        completeness_score=overall_score,
        hallucination=False if overall_score is not None else None,
        overall_score=overall_score,
        evaluation_reason=None,
        duration_ms=duration_ms,
        status=status,
        error_message=None if status == "completed" else "模型不可用",
        created_at=now,
        updated_at=now,
    )


def test_build_run_metrics_only_aggregates_metrics_with_expectations():
    successful = make_result(
        "case_document",
        expected_document_ids=("doc_expected",),
        returned_document_ids=("doc_expected",),
        overall_score=4,
        duration_ms=100,
    )
    failed = make_result(
        "case_chunk",
        status="failed",
        expected_chunk_ids=("chunk_expected",),
        returned_chunk_ids=("chunk_other",),
        duration_ms=50,
    )
    without_expectation = make_result("case_unlabeled", duration_ms=25)

    metrics = build_run_metrics([successful, failed, without_expectation])

    assert metrics == {
        "case_count": 3,
        "completed_count": 2,
        "failed_count": 1,
        "success_rate": 2 / 3,
        "average_duration_ms": 175 / 3,
        "document_hit_rate": 1.0,
        "document_hit_case_count": 1,
        "chunk_hit_rate": 0.0,
        "chunk_hit_case_count": 1,
        "citation_hit_rate": 0.5,
        "citation_hit_case_count": 2,
        "average_overall_score": 4.0,
        "average_faithfulness_score": 4.0,
        "average_relevance_score": 4.0,
        "average_citation_score": 4.0,
        "average_completeness_score": 4.0,
        "evaluated_case_count": 1,
    }


def test_compare_run_metrics_identifies_scored_and_retrieval_regression():
    baseline = make_result(
        "case_target",
        expected_document_ids=("doc_expected",),
        returned_document_ids=("doc_expected",),
        overall_score=5,
        duration_ms=20,
    )
    candidate = make_result(
        "case_target",
        expected_document_ids=("doc_expected",),
        returned_document_ids=(),
        overall_score=3,
        duration_ms=30,
    )

    comparison = compare_run_metrics([baseline], [candidate])

    assert comparison["metric_deltas"]["average_overall_score"] == -2.0
    assert comparison["metric_deltas"]["document_hit_rate"] == -1.0
    assert comparison["metric_deltas"]["average_duration_ms"] == 10.0
    assert comparison["degraded_case_ids"] == ["case_target"]


class InMemoryBenchmarkRepository:
    def __init__(self, run: BenchmarkRun):
        self.run = run
        self.results: list[BenchmarkCaseResult] = []

    async def update_run(self, run: BenchmarkRun) -> BenchmarkRun:
        self.run = deepcopy(run)
        return self.run

    async def insert_case_result(self, result: BenchmarkCaseResult) -> BenchmarkCaseResult:
        self.results.append(result)
        return result


def make_case(case_id: str, question: str) -> BenchmarkCase:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return BenchmarkCase(
        id=case_id,
        user_id="user_target",
        knowledge_base_id="kb_target",
        question=question,
        expected_answer=None,
        expected_document_ids=["doc_target"],
        expected_chunk_ids=[],
        tags=["smoke"],
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def make_run() -> BenchmarkRun:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return BenchmarkRun(
        id="run_target",
        user_id="user_target",
        knowledge_base_id="kb_target",
        task_id=None,
        status="queued",
        config_snapshot={"config_version": 7, "retrieval": {"top_k": 2}},
        case_snapshot=[],
        case_count=2,
        metrics=None,
        error_message=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )


def test_execute_benchmark_run_persists_success_and_failure_with_frozen_snapshot():
    repository = InMemoryBenchmarkRepository(make_run())
    observed_snapshots: list[dict[str, object]] = []

    async def answer_case(question: str, snapshot: dict[str, object]):
        observed_snapshots.append(deepcopy(snapshot))
        if question == "失败问题":
            raise RuntimeError("LLM unavailable")
        return "成功回答", [{"document_id": "doc_target", "chunk_id": "chunk_target"}]

    async def evaluate_answer(_question: str, _answer: str, _sources):
        return {
            "faithfulness_score": 5,
            "relevance_score": 4,
            "citation_score": 5,
            "completeness_score": 4,
            "hallucination": False,
            "overall_score": 4,
            "reason": "通过",
        }

    completed = asyncio.run(
        execute_benchmark_run_cases(
            repository,
            repository.run,
            [make_case("case_success", "成功问题"), make_case("case_failure", "失败问题")],
            answer_case,
            evaluate_answer,
        )
    )

    assert completed.status == "completed_with_errors"
    assert completed.metrics["completed_count"] == 1
    assert completed.metrics["failed_count"] == 1
    assert [result.status for result in repository.results] == ["completed", "failed"]
    assert repository.results[0].retrieval_document_hit is True
    assert repository.results[1].error_message == "Benchmark case execution failed"
    assert observed_snapshots == [repository.run.config_snapshot, repository.run.config_snapshot]


def test_benchmark_keeps_retrieval_metrics_when_answer_evaluator_is_unavailable():
    repository = InMemoryBenchmarkRepository(make_run())

    async def answer_case(_question: str, _snapshot: dict[str, object]):
        return "回答", [{"document_id": "doc_target", "chunk_id": "chunk_target"}]

    async def unavailable_evaluator(_question: str, _answer: str, _sources):
        raise DeepSeekConfigurationError("missing")

    completed = asyncio.run(
        execute_benchmark_run_cases(
            repository, repository.run, [make_case("case_target", "问题")], answer_case, unavailable_evaluator
        )
    )

    result = repository.results[0]
    assert completed.status == "failed"
    assert result.status == "failed"
    assert result.answer == "回答"
    assert result.retrieval_document_hit is True
    assert result.error_message == "Answer evaluator is not configured"


class InMemoryRunSubmissionRepository:
    def __init__(self, cases: list[BenchmarkCase]):
        self.cases = cases
        self.active_run: BenchmarkRun | None = None
        self.inserted: list[BenchmarkRun] = []

    async def list_enabled_cases(self, knowledge_base_id: str, user_id: str):
        return [
            case
            for case in self.cases
            if case.knowledge_base_id == knowledge_base_id and case.user_id == user_id
        ]

    async def get_active_run(self, knowledge_base_id: str, user_id: str):
        return self.active_run

    async def insert_run(self, run: BenchmarkRun):
        self.inserted.append(deepcopy(run))
        self.active_run = run
        return run


def test_create_benchmark_run_freezes_config_and_reuses_active_run():
    repository = InMemoryRunSubmissionRepository([make_case("case_target", "问题")])
    config = KnowledgeBaseConfig(
        knowledge_base_id="kb_target",
        user_id="user_target",
        processing=ProcessingConfig(chunk_size=320, embedding_model_name="embed-v1"),
        retrieval=RetrievalConfig(top_k=3, rerank_enabled=True, rerank_model_name="rerank-v1"),
        generation=GenerationConfig(llm_model_name="llm-v1", temperature=0.6),
        version=9,
    )

    submission = asyncio.run(
        create_benchmark_run(
            repository,
            knowledge_base_id="kb_target",
            user_id="user_target",
            config=config,
            evaluator_model="deepseek-test",
            application_version="test-version",
        )
    )
    config.retrieval.top_k = 99
    duplicate = asyncio.run(
        create_benchmark_run(
            repository,
            knowledge_base_id="kb_target",
            user_id="user_target",
            config=config,
            evaluator_model="deepseek-test",
            application_version="test-version",
        )
    )

    assert submission.created is True
    assert submission.run.config_snapshot["config_version"] == 9
    assert submission.run.config_snapshot["retrieval"]["top_k"] == 3
    assert submission.run.config_snapshot["models"] == {
        "embedding": "embed-v1",
        "rerank": "rerank-v1",
        "llm": "llm-v1",
        "evaluator": "deepseek-test",
    }
    assert duplicate.created is False
    assert duplicate.run.id == submission.run.id
    assert len(repository.inserted) == 1
    repository.cases.clear()
    frozen_cases = benchmark_cases_from_snapshot(submission.run)
    assert [case.question for case in frozen_cases] == ["问题"]


def test_benchmark_run_snapshots_keep_two_knowledge_base_configs_isolated():
    first_case = make_case("case_first", "第一题")
    second_case = make_case("case_second", "第二题")
    second_case.knowledge_base_id = "kb_second"
    repository = InMemoryRunSubmissionRepository([first_case, second_case])
    first_config = KnowledgeBaseConfig(
        knowledge_base_id="kb_target", user_id="user_target",
        processing=ProcessingConfig(embedding_model_name="embed-first"),
        retrieval=RetrievalConfig(top_k=2), generation=GenerationConfig(llm_model_name="llm-first"), version=1,
    )
    second_config = KnowledgeBaseConfig(
        knowledge_base_id="kb_second", user_id="user_target",
        processing=ProcessingConfig(embedding_model_name="embed-second"),
        retrieval=RetrievalConfig(top_k=8), generation=GenerationConfig(llm_model_name="llm-second"), version=2,
    )

    first = asyncio.run(create_benchmark_run(repository, knowledge_base_id="kb_target", user_id="user_target", config=first_config, evaluator_model="deepseek", application_version="test"))
    repository.active_run = None
    second = asyncio.run(create_benchmark_run(repository, knowledge_base_id="kb_second", user_id="user_target", config=second_config, evaluator_model="deepseek", application_version="test"))

    assert first.run.config_snapshot["retrieval"]["top_k"] == 2
    assert first.run.config_snapshot["models"]["embedding"] == "embed-first"
    assert second.run.config_snapshot["retrieval"]["top_k"] == 8
    assert second.run.config_snapshot["models"]["embedding"] == "embed-second"


class InMemoryBenchmarkApiRepository(InMemoryRunSubmissionRepository):
    def __init__(self):
        super().__init__([])
        self.runs: list[BenchmarkRun] = []

    async def replace_cases(self, user_id, knowledge_base_id, cases):
        self.cases = list(cases)
        return cases

    async def insert_cases(self, cases):
        self.cases.extend(cases)
        return cases

    async def list_cases(self, knowledge_base_id, user_id):
        return [case for case in self.cases if case.knowledge_base_id == knowledge_base_id and case.user_id == user_id]

    async def insert_run(self, run):
        self.runs.append(run)
        self.active_run = run
        return run

    async def update_run(self, run):
        return run

    async def get_run(self, run_id, knowledge_base_id, user_id):
        return next((run for run in self.runs if run.id == run_id and run.knowledge_base_id == knowledge_base_id and run.user_id == user_id), None)

    async def list_runs(self, knowledge_base_id, user_id, limit=50):
        return [run for run in self.runs if run.knowledge_base_id == knowledge_base_id and run.user_id == user_id][:limit]

    async def insert_case_result(self, result):
        return result

    async def list_case_results(self, run_id, user_id):
        return []


class InMemoryBenchmarkKnowledgeBaseRepository:
    def __init__(self, item):
        self.item = item

    async def get_active_by_id_and_user(self, kb_id, user_id):
        return self.item if self.item.id == kb_id and self.item.user_id == user_id else None


class RecordingBenchmarkTaskDispatcher:
    def __init__(self):
        self.calls = []

    def delay(self, user_id, knowledge_base_id, run_id):
        self.calls.append((user_id, knowledge_base_id, run_id))
        return type("Task", (), {"id": "task_benchmark"})()


def test_benchmark_api_imports_cases_and_enqueues_one_user_scoped_run():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    knowledge_base = KnowledgeBase(
        id="kb_target", user_id="default_user", name="知识库", description=None,
        status="active", created_at=now, updated_at=now,
    )
    repository = InMemoryBenchmarkApiRepository()
    dispatcher = RecordingBenchmarkTaskDispatcher()
    app.dependency_overrides[get_benchmark_repository] = lambda: repository
    app.dependency_overrides[get_benchmark_knowledge_base_repository] = lambda: InMemoryBenchmarkKnowledgeBaseRepository(knowledge_base)
    app.dependency_overrides[get_benchmark_task_dispatcher] = lambda: dispatcher
    try:
        client = TestClient(app)
        imported = client.post(
            "/api/knowledge-bases/kb_target/benchmarks/import",
            json={"items": [{"question": "标准问题", "expected_document_ids": ["doc_target"]}]},
        )
        submitted = client.post("/api/knowledge-bases/kb_target/benchmark-runs")
    finally:
        app.dependency_overrides.clear()

    assert imported.status_code == 200
    assert imported.json()["items"][0]["question"] == "标准问题"
    assert submitted.status_code == 202
    assert submitted.json()["status"] == "queued"
    assert submitted.json()["task_id"] == "task_benchmark"
    assert dispatcher.calls == [("default_user", "kb_target", submitted.json()["id"])]


def test_benchmark_api_hides_another_users_knowledge_base():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    knowledge_base = KnowledgeBase(
        id="kb_target", user_id="default_user", name="知识库", description=None,
        status="active", created_at=now, updated_at=now,
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="other_user", username="other")
    app.dependency_overrides[get_benchmark_repository] = InMemoryBenchmarkApiRepository
    app.dependency_overrides[get_benchmark_knowledge_base_repository] = lambda: InMemoryBenchmarkKnowledgeBaseRepository(knowledge_base)
    try:
        response = TestClient(app).get("/api/knowledge-bases/kb_target/benchmarks")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_benchmark_api_imports_and_exports_csv():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    knowledge_base = KnowledgeBase(
        id="kb_target", user_id="default_user", name="知识库", description=None,
        status="active", created_at=now, updated_at=now,
    )
    repository = InMemoryBenchmarkApiRepository()
    app.dependency_overrides[get_benchmark_repository] = lambda: repository
    app.dependency_overrides[get_benchmark_knowledge_base_repository] = lambda: InMemoryBenchmarkKnowledgeBaseRepository(knowledge_base)
    try:
        client = TestClient(app)
        imported = client.post(
            "/api/knowledge-bases/kb_target/benchmarks/import/csv",
            params={"mode": "replace"},
            content='question,expected_document_ids,tags\nCSV 问题,"[""doc_csv""]","[""smoke""]"\n',
            headers={"Content-Type": "text/csv"},
        )
        exported = client.get("/api/knowledge-bases/kb_target/benchmarks/export?format=csv")
    finally:
        app.dependency_overrides.clear()

    assert imported.status_code == 200
    assert imported.json()["items"][0]["expected_document_ids"] == ["doc_csv"]
    assert exported.status_code == 200
    assert "CSV 问题" in exported.text
    assert "doc_csv" in exported.text
