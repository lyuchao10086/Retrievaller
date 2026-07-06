from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes.document import (
    get_document_repository,
    get_document_storage,
    get_knowledge_base_repository,
    get_parse_task_dispatcher,
)
from app.main import app
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.document import (
    DEFAULT_DOCUMENT_BUCKET,
    PARSED_STATUS,
    PARSING_STATUS,
    UPLOADED_STATUS,
    delete_document,
    get_document_by_id,
    list_documents_by_knowledge_base,
    parse_document,
    upload_document_to_knowledge_base,
)
from app.services.document import DocumentStatusError
from app.services.knowledge_base import DEFAULT_USER_ID


class InMemoryKnowledgeBaseRepository:
    def __init__(self, items=None):
        self.items = items or []

    async def get_active_by_id_and_user(self, kb_id, user_id):
        for item in self.items:
            if item.id == kb_id and item.user_id == user_id and item.status == "active":
                return item
        return None


class InMemoryDocumentRepository:
    def __init__(self):
        self.items = []
        self.status_updates = []

    async def insert(self, document):
        self.items.append(document)
        return document

    async def list_by_knowledge_base(self, user_id, knowledge_base_id):
        return [
            item
            for item in self.items
            if item.user_id == user_id
            and item.knowledge_base_id == knowledge_base_id
            and item.status != "deleted"
        ]

    async def get_by_id_and_knowledge_base(
        self,
        user_id,
        knowledge_base_id,
        document_id,
    ):
        for item in self.items:
            if (
                item.user_id == user_id
                and item.knowledge_base_id == knowledge_base_id
                and item.id == document_id
                and item.status != "deleted"
            ):
                return item
        return None

    async def soft_delete_by_id_and_knowledge_base(
        self,
        user_id,
        knowledge_base_id,
        document_id,
        deleted_at,
    ):
        document = await self.get_by_id_and_knowledge_base(
            user_id,
            knowledge_base_id,
            document_id,
        )
        if document is None:
            return None
        document.status = "deleted"
        document.updated_at = deleted_at
        return document

    async def update_status_by_id_and_knowledge_base(
        self,
        user_id,
        knowledge_base_id,
        document_id,
        status,
        error_message,
        updated_at,
    ):
        document = await self.get_by_id_and_knowledge_base(
            user_id,
            knowledge_base_id,
            document_id,
        )
        if document is None:
            return None
        document.status = status
        document.error_message = error_message
        document.updated_at = updated_at
        self.status_updates.append(status)
        return document

    async def set_task_id_by_id_and_knowledge_base(
        self,
        user_id,
        knowledge_base_id,
        document_id,
        task_id,
        updated_at,
    ):
        document = await self.get_by_id_and_knowledge_base(
            user_id,
            knowledge_base_id,
            document_id,
        )
        if document is None:
            return None
        document.task_id = task_id
        document.updated_at = updated_at
        return document


class InMemoryDocumentStorage:
    def __init__(self):
        self.created_buckets = []
        self.objects = {}

    async def ensure_bucket(self, bucket_name):
        self.created_buckets.append(bucket_name)

    async def put_object(self, bucket_name, object_key, data, content_type):
        self.objects[(bucket_name, object_key)] = {
            "data": data,
            "content_type": content_type,
        }


class FakeParseTaskDispatcher:
    def __init__(self, task_id="task_test_123"):
        self.task_id = task_id
        self.calls = []

    def submit(self, kb_id, document_id, user_id):
        self.calls.append(
            {
                "kb_id": kb_id,
                "document_id": document_id,
                "user_id": user_id,
            }
        )
        return self.task_id


def test_upload_document_requires_active_knowledge_base():
    knowledge_base_repository = InMemoryKnowledgeBaseRepository()
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()

    document = run_async(
        upload_document_to_knowledge_base(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            storage=storage,
            kb_id="kb_missing",
            file_name="demo.txt",
            file_type="text/plain",
            content=b"hello",
        )
    )

    assert document is None
    assert document_repository.items == []
    assert storage.objects == {}


def test_upload_document_saves_raw_file_and_document_record():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()

    document = run_async(
        upload_document_to_knowledge_base(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            storage=storage,
            kb_id=knowledge_base.id,
            file_name="demo.txt",
            file_type="text/plain",
            content=b"hello",
        )
    )

    assert document is not None
    assert document.id.startswith("doc_")
    assert document.user_id == DEFAULT_USER_ID
    assert document.knowledge_base_id == knowledge_base.id
    assert document.file_name == "demo.txt"
    assert document.file_type == "text/plain"
    assert document.file_size == 5
    assert document.storage_bucket == DEFAULT_DOCUMENT_BUCKET
    assert document.storage_object_key == (
        f"users/{DEFAULT_USER_ID}/knowledge_bases/{knowledge_base.id}"
        f"/raw/{document.id}/demo.txt"
    )
    assert document.status == UPLOADED_STATUS
    assert document.error_message is None
    assert document.created_at is not None
    assert document.updated_at is not None

    assert storage.created_buckets == [DEFAULT_DOCUMENT_BUCKET]
    assert storage.objects[
        (DEFAULT_DOCUMENT_BUCKET, document.storage_object_key)
    ] == {"data": b"hello", "content_type": "text/plain"}
    assert document_repository.items == [document]


def test_list_documents_only_returns_default_user_knowledge_base_documents():
    document_repository = InMemoryDocumentRepository()
    target = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    other_kb = make_document("doc_other_kb", "kb_other", DEFAULT_USER_ID)
    other_user = make_document("doc_other_user", "kb_target", "other_user")
    document_repository.items.extend([target, other_kb, other_user])

    documents = run_async(
        list_documents_by_knowledge_base(document_repository, "kb_target")
    )

    assert documents == [target]


def test_get_document_by_id_requires_default_user_and_knowledge_base():
    document_repository = InMemoryDocumentRepository()
    target = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    other_kb = make_document("doc_target", "kb_other", DEFAULT_USER_ID)
    other_user = make_document("doc_other_user", "kb_target", "other_user")
    document_repository.items.extend([target, other_kb, other_user])

    found = run_async(
        get_document_by_id(document_repository, "kb_target", "doc_target")
    )
    wrong_kb = run_async(
        get_document_by_id(document_repository, "kb_wrong", "doc_target")
    )
    missing = run_async(
        get_document_by_id(document_repository, "kb_target", "doc_missing")
    )

    assert found == target
    assert wrong_kb is None
    assert missing is None


def test_delete_document_soft_deletes_default_user_knowledge_base_document():
    document_repository = InMemoryDocumentRepository()
    target = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    original_updated_at = target.updated_at
    document_repository.items.append(target)

    deleted = run_async(
        delete_document(document_repository, "kb_target", "doc_target")
    )
    listed_documents = run_async(
        list_documents_by_knowledge_base(document_repository, "kb_target")
    )
    found_after_delete = run_async(
        get_document_by_id(document_repository, "kb_target", "doc_target")
    )

    assert deleted is not None
    assert deleted.id == target.id
    assert deleted.status == "deleted"
    assert deleted.updated_at > original_updated_at
    assert listed_documents == []
    assert found_after_delete is None


def test_delete_document_requires_default_user_and_knowledge_base():
    document_repository = InMemoryDocumentRepository()
    target = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    other_kb = make_document("doc_target", "kb_other", DEFAULT_USER_ID)
    other_user = make_document("doc_other_user", "kb_target", "other_user")
    document_repository.items.extend([target, other_kb, other_user])

    wrong_kb = run_async(
        delete_document(document_repository, "kb_wrong", "doc_target")
    )
    missing = run_async(
        delete_document(document_repository, "kb_target", "doc_missing")
    )

    assert wrong_kb is None
    assert missing is None
    assert target.status == UPLOADED_STATUS
    assert other_kb.status == UPLOADED_STATUS
    assert other_user.status == UPLOADED_STATUS


def test_parse_document_transitions_uploaded_document_to_parsed():
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document_repository.items.append(document)

    parsed = run_async(parse_document(document_repository, "kb_target", "doc_target"))

    assert parsed is not None
    assert parsed.id == document.id
    assert parsed.status == PARSED_STATUS
    assert parsed.error_message is None
    assert document_repository.status_updates == [PARSING_STATUS, PARSED_STATUS]


def test_parse_document_rejects_non_uploaded_document():
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.status = PARSED_STATUS
    document_repository.items.append(document)

    try:
        run_async(parse_document(document_repository, "kb_target", "doc_target"))
    except DocumentStatusError as exc:
        error = exc
    else:
        error = None

    assert error is not None
    assert str(error) == "Document status must be uploaded before parsing"
    assert document.status == PARSED_STATUS
    assert document_repository.status_updates == []


def test_parse_document_marks_failed_when_simulated_parse_raises():
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document_repository.items.append(document)

    def failing_parser():
        raise RuntimeError("simulated parser failure")

    parsed = run_async(
        parse_document(
            document_repository,
            "kb_target",
            "doc_target",
            parse_runner=failing_parser,
        )
    )

    assert parsed is not None
    assert parsed.status == "failed"
    assert parsed.error_message == "simulated parser failure"
    assert document_repository.status_updates == [PARSING_STATUS, "failed"]


def test_document_api_can_upload_and_list_documents():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        upload_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/upload",
            files={"file": ("demo.txt", b"hello", "text/plain")},
        )
        list_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents"
        )
    finally:
        app.dependency_overrides.clear()

    assert upload_response.status_code == 201
    uploaded = upload_response.json()
    assert uploaded["id"].startswith("doc_")
    assert uploaded["user_id"] == DEFAULT_USER_ID
    assert uploaded["knowledge_base_id"] == knowledge_base.id
    assert uploaded["file_name"] == "demo.txt"
    assert uploaded["file_type"] == "text/plain"
    assert uploaded["file_size"] == 5
    assert uploaded["storage_bucket"] == DEFAULT_DOCUMENT_BUCKET
    assert uploaded["status"] == UPLOADED_STATUS
    assert uploaded["error_message"] is None

    assert list_response.status_code == 200
    assert list_response.json() == [uploaded]


def test_document_api_can_get_document_detail():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == document.id
    assert response.json()["knowledge_base_id"] == knowledge_base.id
    assert response.json()["user_id"] == DEFAULT_USER_ID


def test_document_api_returns_404_when_detail_knowledge_base_is_missing():
    knowledge_base_repository = InMemoryKnowledgeBaseRepository()
    document_repository = InMemoryDocumentRepository()
    document_repository.items.append(
        make_document("doc_target", "kb_missing", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    try:
        client = TestClient(app)
        response = client.get(
            "/api/knowledge-bases/kb_missing/documents/doc_target"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_document_api_returns_404_when_detail_document_is_not_in_knowledge_base():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document_repository.items.append(
        make_document("doc_target", "kb_other", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    try:
        client = TestClient(app)
        wrong_kb_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/doc_target"
        )
        missing_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/doc_missing"
        )
    finally:
        app.dependency_overrides.clear()

    assert wrong_kb_response.status_code == 404
    assert wrong_kb_response.json() == {"detail": "Document not found"}
    assert missing_response.status_code == 404
    assert missing_response.json() == {"detail": "Document not found"}


def test_document_api_can_soft_delete_document_by_id():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    try:
        client = TestClient(app)
        delete_response = client.delete(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}"
        )
        list_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents"
        )
        detail_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}"
        )
    finally:
        app.dependency_overrides.clear()

    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["id"] == document.id
    assert deleted["knowledge_base_id"] == knowledge_base.id
    assert deleted["user_id"] == DEFAULT_USER_ID
    assert deleted["status"] == "deleted"
    assert list_response.status_code == 200
    assert list_response.json() == []
    assert detail_response.status_code == 404
    assert detail_response.json() == {"detail": "Document not found"}


def test_document_api_returns_404_when_delete_knowledge_base_is_missing():
    knowledge_base_repository = InMemoryKnowledgeBaseRepository()
    document_repository = InMemoryDocumentRepository()
    document_repository.items.append(
        make_document("doc_target", "kb_missing", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    try:
        client = TestClient(app)
        response = client.delete(
            "/api/knowledge-bases/kb_missing/documents/doc_target"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_document_api_returns_404_when_delete_document_is_not_visible():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document_repository.items.append(
        make_document("doc_target", "kb_other", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    try:
        client = TestClient(app)
        response = client.delete(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/doc_target"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


def test_document_api_can_parse_uploaded_document():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document_repository.items.append(document)
    dispatcher = FakeParseTaskDispatcher("celery_task_123")

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_parse_task_dispatcher] = lambda: dispatcher
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/parse"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    submitted = response.json()
    assert submitted == {
        "message": "Parse task submitted",
        "document_id": document.id,
        "task_id": "celery_task_123",
        "status": UPLOADED_STATUS,
    }
    assert document.status == UPLOADED_STATUS
    assert document.task_id == "celery_task_123"
    assert document_repository.status_updates == []
    assert dispatcher.calls == [
        {
            "kb_id": knowledge_base.id,
            "document_id": document.id,
            "user_id": DEFAULT_USER_ID,
        }
    ]


def test_document_api_returns_400_when_parse_document_is_not_uploaded():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document.status = PARSED_STATUS
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_parse_task_dispatcher] = lambda: FakeParseTaskDispatcher()
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/parse"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Document status must be uploaded before parsing"
    }


def test_document_api_returns_404_when_parse_knowledge_base_is_missing():
    knowledge_base_repository = InMemoryKnowledgeBaseRepository()
    document_repository = InMemoryDocumentRepository()
    document_repository.items.append(
        make_document("doc_target", "kb_missing", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_parse_task_dispatcher] = lambda: FakeParseTaskDispatcher()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/knowledge-bases/kb_missing/documents/doc_target/parse"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_document_api_returns_404_when_parse_document_is_not_visible():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document_repository.items.append(
        make_document("doc_target", "kb_other", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_parse_task_dispatcher] = lambda: FakeParseTaskDispatcher()
    try:
        client = TestClient(app)
        wrong_kb_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/doc_target/parse"
        )
        missing_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/doc_missing/parse"
        )
    finally:
        app.dependency_overrides.clear()

    assert wrong_kb_response.status_code == 404
    assert wrong_kb_response.json() == {"detail": "Document not found"}
    assert missing_response.status_code == 404
    assert missing_response.json() == {"detail": "Document not found"}


def test_document_api_returns_404_when_parse_document_is_deleted():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_deleted", knowledge_base.id, DEFAULT_USER_ID)
    document.status = "deleted"
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_parse_task_dispatcher] = lambda: FakeParseTaskDispatcher()
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/parse"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}
    assert document.status == "deleted"


def test_document_api_returns_404_when_uploading_to_missing_knowledge_base():
    knowledge_base_repository = InMemoryKnowledgeBaseRepository()
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.post(
            "/api/knowledge-bases/kb_missing/documents/upload",
            files={"file": ("demo.txt", b"hello", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_document_api_returns_404_when_uploading_to_deleted_knowledge_base():
    deleted_knowledge_base = make_knowledge_base("kb_deleted")
    deleted_knowledge_base.status = "deleted"
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([deleted_knowledge_base])
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{deleted_knowledge_base.id}/documents/upload",
            files={"file": ("demo.txt", b"hello", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}
    assert document_repository.items == []
    assert storage.objects == {}


def make_knowledge_base(kb_id):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return KnowledgeBase(
        id=kb_id,
        user_id=DEFAULT_USER_ID,
        name="测试知识库",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )


def make_document(document_id, knowledge_base_id, user_id):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return Document(
        id=document_id,
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        file_name=f"{document_id}.txt",
        file_type="text/plain",
        file_size=5,
        storage_bucket=DEFAULT_DOCUMENT_BUCKET,
        storage_object_key=(
            f"users/{user_id}/knowledge_bases/{knowledge_base_id}"
            f"/raw/{document_id}/{document_id}.txt"
        ),
        status=UPLOADED_STATUS,
        error_message=None,
        task_id=None,
        created_at=now,
        updated_at=now,
    )


def run_async(coro):
    import asyncio

    return asyncio.run(coro)
