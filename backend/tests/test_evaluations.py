from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes.evaluation import get_evaluation_repository
from app.api.routes.evaluation import (
    get_deepseek_service,
    get_qa_record_repository,
)
from app.main import app
from app.models.evaluation import Evaluation
from app.models.qa_record import QaRecord
from app.services.deepseek_service import (
    DEEPSEEK_API_KEY_NOT_CONFIGURED_MESSAGE,
    DeepSeekConfigurationError,
)
from app.services.knowledge_base import DEFAULT_USER_ID


class InMemoryEvaluationRepository:
    def __init__(self, items=None):
        self.items = items or []

    async def insert(self, evaluation):
        self.items.append(evaluation)
        return evaluation

    async def get_by_qa_record_id_and_user(self, qa_record_id, user_id):
        for item in self.items:
            if item.qa_record_id == qa_record_id and item.user_id == user_id:
                return item
        return None

    async def list_recent_by_user(self, user_id, limit=50):
        return [item for item in self.items if item.user_id == user_id][:limit]


def test_evaluations_api_lists_recent_default_user_results():
    target = make_evaluation("eval_target", "qa_target", DEFAULT_USER_ID)
    other_user = make_evaluation("eval_other", "qa_other", "other_user")
    repository = InMemoryEvaluationRepository([target, other_user])

    app.dependency_overrides[get_evaluation_repository] = lambda: repository
    try:
        response = TestClient(app).get("/api/evaluations")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "id": target.id,
            "qa_record_id": target.qa_record_id,
            "faithfulness_score": target.faithfulness_score,
            "relevance_score": target.relevance_score,
            "citation_score": target.citation_score,
            "completeness_score": target.completeness_score,
            "hallucination": target.hallucination,
            "overall_score": target.overall_score,
            "reason": target.reason,
            "created_at": target.created_at.isoformat(),
        }
    ]


def test_single_knowledge_base_rag_answer_route_is_removed():
    response = TestClient(app).post(
        "/api/knowledge-bases/kb_target/rag/answer",
        json={"query": "hello"},
    )

    assert response.status_code == 404


def test_create_evaluation_returns_clear_error_when_deepseek_key_is_missing():
    qa_record = make_qa_record("qa_target", DEFAULT_USER_ID)
    evaluation_repository = InMemoryEvaluationRepository()

    app.dependency_overrides[get_qa_record_repository] = lambda: InMemoryQaRecordRepository(
        [qa_record]
    )
    app.dependency_overrides[get_evaluation_repository] = lambda: evaluation_repository
    app.dependency_overrides[get_deepseek_service] = lambda: MissingKeyDeepSeekService()
    try:
        response = TestClient(app).post(f"/api/evaluations/qa-records/{qa_record.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": DEEPSEEK_API_KEY_NOT_CONFIGURED_MESSAGE}
    assert evaluation_repository.items == []


def test_create_evaluation_reuses_existing_result_without_calling_deepseek():
    existing = make_evaluation("eval_target", "qa_target", DEFAULT_USER_ID)
    qa_record = make_qa_record("qa_target", DEFAULT_USER_ID)
    deepseek_service = RaisingDeepSeekService()

    app.dependency_overrides[get_qa_record_repository] = lambda: InMemoryQaRecordRepository(
        [qa_record]
    )
    app.dependency_overrides[get_evaluation_repository] = lambda: InMemoryEvaluationRepository(
        [existing]
    )
    app.dependency_overrides[get_deepseek_service] = lambda: deepseek_service
    try:
        response = TestClient(app).post(f"/api/evaluations/qa-records/{qa_record.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == existing.id
    assert deepseek_service.called is False


def make_evaluation(evaluation_id: str, qa_record_id: str, user_id: str) -> Evaluation:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return Evaluation(
        id=evaluation_id,
        user_id=user_id,
        qa_record_id=qa_record_id,
        faithfulness_score=5,
        relevance_score=4,
        citation_score=3,
        completeness_score=4,
        hallucination=False,
        overall_score=4,
        reason="测试评估",
        raw_response="{}",
        created_at=now,
        updated_at=now,
    )


def make_qa_record(record_id: str, user_id: str) -> QaRecord:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return QaRecord(
        id=record_id,
        user_id=user_id,
        title="测试记录",
        question="问题",
        answer="答案",
        knowledge_base_ids=["kb_test"],
        sources_json=[],
        created_at=now,
        updated_at=now,
    )


class InMemoryQaRecordRepository:
    def __init__(self, items=None):
        self.items = items or []

    async def insert(self, record):
        self.items.append(record)
        return record

    async def list_recent_by_user(self, user_id, limit=50):
        return [item for item in self.items if item.user_id == user_id][:limit]

    async def get_by_id_and_user(self, qa_record_id, user_id):
        for item in self.items:
            if item.id == qa_record_id and item.user_id == user_id:
                return item
        return None

    async def delete_by_id_and_user(self, qa_record_id, user_id):
        return None


class MissingKeyDeepSeekService:
    async def chat(self, system_prompt, user_prompt):
        raise DeepSeekConfigurationError(DEEPSEEK_API_KEY_NOT_CONFIGURED_MESSAGE)


class RaisingDeepSeekService:
    def __init__(self):
        self.called = False

    async def chat(self, system_prompt, user_prompt):
        self.called = True
        raise AssertionError("DeepSeek should not be called when evaluation exists")
