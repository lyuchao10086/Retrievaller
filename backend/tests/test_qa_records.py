from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes.rag import get_qa_record_repository
from app.main import app
from app.models.qa_record import QaRecord
from app.services.knowledge_base import DEFAULT_USER_ID
from app.services.qa_record import delete_qa_record, list_qa_records


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
        record = await self.get_by_id_and_user(qa_record_id, user_id)
        if record is None:
            return None
        self.items = [item for item in self.items if item is not record]
        return record


def test_delete_qa_record_hard_deletes_default_user_record():
    target = make_qa_record("qa_target", DEFAULT_USER_ID)
    other_user = make_qa_record("qa_other", "other_user")
    repository = InMemoryQaRecordRepository([target, other_user])

    deleted = run_async(delete_qa_record(repository, target.id))
    records = run_async(list_qa_records(repository))

    assert deleted == target
    assert target not in repository.items
    assert records == []
    assert other_user in repository.items


def test_rag_records_api_lists_default_user_records():
    target = make_qa_record("qa_target", DEFAULT_USER_ID)
    other_user = make_qa_record("qa_other", "other_user")
    repository = InMemoryQaRecordRepository([target, other_user])

    app.dependency_overrides[get_qa_record_repository] = lambda: repository
    try:
        response = TestClient(app).get("/api/rag/records")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": target.id,
            "title": target.title,
            "question": target.question,
            "answer": target.answer,
            "knowledge_base_ids": target.knowledge_base_ids,
            "sources_json": target.sources_json,
            "created_at": target.created_at.isoformat(),
        }
    ]


def test_rag_records_api_can_hard_delete_record_by_id():
    target = make_qa_record("qa_target", DEFAULT_USER_ID)
    repository = InMemoryQaRecordRepository([target])

    app.dependency_overrides[get_qa_record_repository] = lambda: repository
    try:
        client = TestClient(app)
        delete_response = client.delete(f"/api/rag/records/{target.id}")
        list_response = client.get("/api/rag/records")
        second_delete_response = client.delete(f"/api/rag/records/{target.id}")
    finally:
        app.dependency_overrides.clear()

    assert delete_response.status_code == 200
    assert delete_response.json()["id"] == target.id
    assert list_response.status_code == 200
    assert list_response.json() == []
    assert second_delete_response.status_code == 404
    assert second_delete_response.json() == {"detail": "Qa record not found"}


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


def run_async(coro):
    import asyncio

    return asyncio.run(coro)
