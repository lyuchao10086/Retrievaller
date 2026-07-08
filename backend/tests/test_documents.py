import json
from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient

from app.api.routes.document import (
    get_document_repository,
    get_document_storage,
    get_knowledge_base_repository,
    get_vector_service,
)
from app.main import app
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.document import (
    DEFAULT_DOCUMENT_BUCKET,
    UPLOADED_STATUS,
    delete_document,
    get_document_by_id,
    list_documents_by_knowledge_base,
    upload_document_to_knowledge_base,
)
from app.services.embedding_service import OllamaEmbeddingService
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

    async def delete_by_id_and_knowledge_base(
        self,
        user_id,
        knowledge_base_id,
        document_id,
    ):
        document = await self.get_by_id_and_knowledge_base(
            user_id,
            knowledge_base_id,
            document_id,
        )
        if document is None:
            return None
        self.items = [item for item in self.items if item is not document]
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

    async def set_parse_result_by_id_and_knowledge_base(
        self,
        user_id,
        knowledge_base_id,
        document_id,
        parsed_bucket,
        parsed_object_key,
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
        document.parsed_bucket = parsed_bucket
        document.parsed_object_key = parsed_object_key
        document.status = status
        document.error_message = error_message
        document.updated_at = updated_at
        self.status_updates.append(status)
        return document


class FakeVectorService:
    def __init__(self):
        self.calls = []
        self.deleted_documents = []
        self.deleted_knowledge_bases = []

    def insert_chunk_embeddings(self, chunks, embeddings):
        self.calls.append(
            {
                "chunk_ids": [chunk.id for chunk in chunks],
                "embeddings": embeddings,
            }
        )
        return [f"vector_{chunk.id}" for chunk in chunks]

    def delete_chunk_embeddings_by_document(self, user_id, knowledge_base_id, document_id):
        self.deleted_documents.append(
            {
                "user_id": user_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
            }
        )

    def delete_chunk_embeddings_by_knowledge_base(self, user_id, knowledge_base_id):
        self.deleted_knowledge_bases.append(
            {
                "user_id": user_id,
                "knowledge_base_id": knowledge_base_id,
            }
        )


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

    async def get_object(self, bucket_name, object_key):
        return self.objects[(bucket_name, object_key)]["data"]

    async def delete_object(self, bucket_name, object_key):
        self.objects.pop((bucket_name, object_key), None)


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


def test_ollama_embedding_service_calls_batch_embed_api():
    requests = []

    def handler(request):
        requests.append(
            {
                "url": str(request.url),
                "body": json.loads(request.content.decode("utf-8")),
            }
        )
        return httpx.Response(200, json={"embeddings": [[1, 2], [3, 4]]})

    service = OllamaEmbeddingService(
        model_name="quentinz/bge-large-zh-v1.5:latest",
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )

    embeddings = service.embed_texts(["你好", "检索"])

    assert embeddings == [[1.0, 2.0], [3.0, 4.0]]
    assert requests == [
        {
            "url": "http://ollama.test/api/embed",
            "body": {
                "model": "quentinz/bge-large-zh-v1.5:latest",
                "input": ["你好", "检索"],
            },
        }
    ]


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


def test_delete_document_hard_deletes_default_user_knowledge_base_document():
    document_repository = InMemoryDocumentRepository()
    target = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
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
    assert target not in document_repository.items
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


def test_document_api_can_hard_delete_document_by_id():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    vector_service = FakeVectorService()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document.parsed_bucket = "rag-parsed-results"
    document.parsed_object_key = "parsed/doc_target.json"
    document_repository.items.append(document)
    storage = InMemoryDocumentStorage()
    storage.objects[(document.storage_bucket, document.storage_object_key)] = {
        "data": b"raw",
        "content_type": document.file_type,
    }
    storage.objects[(document.parsed_bucket, document.parsed_object_key)] = {
        "data": b"{}",
        "content_type": "application/json",
    }

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        delete_response = client.delete(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}"
        )
        list_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents"
        )
    finally:
        app.dependency_overrides.clear()

    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["id"] == document.id
    assert deleted["knowledge_base_id"] == knowledge_base.id
    assert deleted["user_id"] == DEFAULT_USER_ID
    assert deleted["status"] == UPLOADED_STATUS
    assert document not in document_repository.items
    assert vector_service.deleted_documents == [
        {
            "user_id": DEFAULT_USER_ID,
            "knowledge_base_id": knowledge_base.id,
            "document_id": document.id,
        }
    ]
    assert (document.storage_bucket, document.storage_object_key) not in storage.objects
    assert (document.parsed_bucket, document.parsed_object_key) not in storage.objects
    assert list_response.status_code == 200
    assert list_response.json() == []


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
        parsed_bucket=None,
        parsed_object_key=None,
        task_id=None,
        created_at=now,
        updated_at=now,
    )


def run_async(coro):
    import asyncio

    return asyncio.run(coro)
