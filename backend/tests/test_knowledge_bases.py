from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes.knowledge_base import (
    get_document_repository,
    get_document_storage,
    get_knowledge_base_repository,
    get_vector_service,
)
from app.main import app
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.repositories.knowledge_base import MySQLKnowledgeBaseRepository
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.services.knowledge_base import (
    DEFAULT_USER_ID,
    create_knowledge_base,
    delete_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    update_knowledge_base,
)


class InMemoryKnowledgeBaseRepository:
    def __init__(self):
        self.items = []

    async def insert(self, knowledge_base):
        self.items.append(knowledge_base)
        return knowledge_base

    async def list_active_by_user(self, user_id):
        return [
            item
            for item in self.items
            if item.user_id == user_id and item.status == "active"
        ]

    async def get_active_by_id_and_user(self, kb_id, user_id):
        for item in self.items:
            if item.id == kb_id and item.user_id == user_id and item.status == "active":
                return item
        return None

    async def update_active_by_id_and_user(self, kb_id, user_id, updates):
        knowledge_base = await self.get_active_by_id_and_user(kb_id, user_id)
        if knowledge_base is None:
            return None
        for field_name, value in updates.items():
            setattr(knowledge_base, field_name, value)
        return knowledge_base

    async def delete_active_by_id_and_user(self, kb_id, user_id):
        knowledge_base = await self.get_active_by_id_and_user(kb_id, user_id)
        if knowledge_base is None:
            return None
        self.items = [item for item in self.items if item is not knowledge_base]
        return knowledge_base


class RecordingMySQLCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 0
        self._row = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.connection.statements.append(normalized)
        if normalized.startswith("SELECT"):
            self._row = self.connection.knowledge_base_row
        elif "DELETE FROM knowledge_bases" in normalized:
            self.rowcount = 1

    async def fetchone(self):
        return self._row


class RecordingMySQLConnection:
    def __init__(self, knowledge_base_row):
        self.knowledge_base_row = knowledge_base_row
        self.statements = []
        self.commit_count = 0

    def cursor(self, *_args, **_kwargs):
        return RecordingMySQLCursor(self)

    async def commit(self):
        self.commit_count += 1


class FakeVectorService:
    def __init__(self):
        self.deleted_knowledge_bases = []

    def delete_chunk_embeddings_by_knowledge_base(self, user_id, knowledge_base_id):
        self.deleted_knowledge_bases.append(
            {
                "user_id": user_id,
                "knowledge_base_id": knowledge_base_id,
            }
        )


class InMemoryDocumentRepository:
    def __init__(self):
        self.items = []

    async def list_by_knowledge_base(self, user_id, knowledge_base_id):
        return [
            item
            for item in self.items
            if item.user_id == user_id and item.knowledge_base_id == knowledge_base_id
        ]


class InMemoryDocumentStorage:
    def __init__(self):
        self.objects = {}

    async def delete_object(self, bucket_name, object_key):
        self.objects.pop((bucket_name, object_key), None)


def test_create_knowledge_base_uses_default_user_and_active_status():
    repository = InMemoryKnowledgeBaseRepository()

    created = run_async(
        create_knowledge_base(
            repository,
            KnowledgeBaseCreate(name="法律资料库", description="合同与法规资料"),
        )
    )

    assert created.id.startswith("kb_")
    assert created.user_id == DEFAULT_USER_ID
    assert created.name == "法律资料库"
    assert created.description == "合同与法规资料"
    assert created.status == "active"
    assert created.created_at is not None
    assert created.updated_at is not None


def test_list_knowledge_bases_only_returns_active_default_user_items():
    repository = InMemoryKnowledgeBaseRepository()
    active = run_async(
        create_knowledge_base(
            repository,
            KnowledgeBaseCreate(name="默认用户 active"),
        )
    )
    repository.items.append(
        KnowledgeBase(
            id="kb_inactive",
            user_id=DEFAULT_USER_ID,
            name="默认用户 inactive",
            description=None,
            status="archived",
            created_at=active.created_at,
            updated_at=active.updated_at,
        )
    )
    repository.items.append(
        KnowledgeBase(
            id="kb_other_user",
            user_id="other_user",
            name="其他用户 active",
            description=None,
            status="active",
            created_at=active.created_at,
            updated_at=active.updated_at,
        )
    )

    items = run_async(list_knowledge_bases(repository))

    assert [item.name for item in items] == ["默认用户 active"]


def test_get_knowledge_base_only_returns_active_default_user_item():
    repository = InMemoryKnowledgeBaseRepository()
    active = run_async(
        create_knowledge_base(
            repository,
            KnowledgeBaseCreate(name="默认用户 active"),
        )
    )
    repository.items.append(
        KnowledgeBase(
            id="kb_inactive",
            user_id=DEFAULT_USER_ID,
            name="默认用户 inactive",
            description=None,
            status="archived",
            created_at=active.created_at,
            updated_at=active.updated_at,
        )
    )
    repository.items.append(
        KnowledgeBase(
            id="kb_other_user",
            user_id="other_user",
            name="其他用户 active",
            description=None,
            status="active",
            created_at=active.created_at,
            updated_at=active.updated_at,
        )
    )

    found = run_async(get_knowledge_base(repository, active.id))
    inactive = run_async(get_knowledge_base(repository, "kb_inactive"))
    other_user = run_async(get_knowledge_base(repository, "kb_other_user"))
    missing = run_async(get_knowledge_base(repository, "kb_missing"))

    assert found == active
    assert inactive is None
    assert other_user is None
    assert missing is None


def test_update_knowledge_base_only_updates_active_default_user_item():
    repository = InMemoryKnowledgeBaseRepository()
    active = run_async(
        create_knowledge_base(
            repository,
            KnowledgeBaseCreate(name="旧名称", description="旧描述"),
        )
    )
    original_updated_at = active.updated_at
    repository.items.append(
        KnowledgeBase(
            id="kb_other_user",
            user_id="other_user",
            name="其他用户 active",
            description=None,
            status="active",
            created_at=active.created_at,
            updated_at=active.updated_at,
        )
    )

    updated = run_async(
        update_knowledge_base(
            repository,
            active.id,
            KnowledgeBaseUpdate(name="新名称", description="新描述"),
        )
    )
    other_user = run_async(
        update_knowledge_base(
            repository,
            "kb_other_user",
            KnowledgeBaseUpdate(name="不该更新"),
        )
    )

    assert updated is not None
    assert updated.id == active.id
    assert updated.name == "新名称"
    assert updated.description == "新描述"
    assert updated.user_id == DEFAULT_USER_ID
    assert updated.status == "active"
    assert updated.updated_at > original_updated_at
    assert other_user is None


def test_delete_knowledge_base_hard_deletes_active_default_user_item():
    repository = InMemoryKnowledgeBaseRepository()
    active = run_async(
        create_knowledge_base(
            repository,
            KnowledgeBaseCreate(name="待删除", description="硬删除"),
        )
    )

    deleted = run_async(delete_knowledge_base(repository, active.id))
    listed_items = run_async(list_knowledge_bases(repository))
    found_after_delete = run_async(get_knowledge_base(repository, active.id))

    assert deleted is not None
    assert deleted.id == active.id
    assert active not in repository.items
    assert listed_items == []
    assert found_after_delete is None


def test_delete_knowledge_base_only_deletes_active_default_user_item():
    repository = InMemoryKnowledgeBaseRepository()
    active = run_async(
        create_knowledge_base(
            repository,
            KnowledgeBaseCreate(name="默认用户 active"),
        )
    )
    repository.items.append(
        KnowledgeBase(
            id="kb_other_user",
            user_id="other_user",
            name="其他用户 active",
            description=None,
            status="active",
            created_at=active.created_at,
            updated_at=active.updated_at,
        )
    )

    other_user = run_async(delete_knowledge_base(repository, "kb_other_user"))
    missing = run_async(delete_knowledge_base(repository, "kb_missing"))

    assert other_user is None
    assert missing is None


def test_mysql_delete_knowledge_base_removes_config_before_parent_record():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    connection = RecordingMySQLConnection(
        {
            "id": "kb_target",
            "user_id": DEFAULT_USER_ID,
            "name": "待删除知识库",
            "description": None,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )
    repository = MySQLKnowledgeBaseRepository(connection)

    deleted = run_async(
        repository.delete_active_by_id_and_user("kb_target", DEFAULT_USER_ID)
    )

    config_delete_index = next(
        index
        for index, statement in enumerate(connection.statements)
        if "DELETE FROM knowledge_base_configs" in statement
    )
    knowledge_base_delete_index = next(
        index
        for index, statement in enumerate(connection.statements)
        if "DELETE FROM knowledge_bases" in statement
    )
    assert deleted is not None
    assert config_delete_index < knowledge_base_delete_index
    assert connection.commit_count == 1


def test_knowledge_base_api_can_create_and_list_items():
    repository = InMemoryKnowledgeBaseRepository()

    async def override_get_knowledge_base_repository():
        return repository

    app.dependency_overrides[
        get_knowledge_base_repository
    ] = override_get_knowledge_base_repository
    try:
        client = TestClient(app)
        create_response = client.post(
            "/api/knowledge-bases",
            json={"name": "项目文档", "description": "研发资料"},
        )
        list_response = client.get("/api/knowledge-bases")
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["id"].startswith("kb_")
    assert created["user_id"] == DEFAULT_USER_ID
    assert created["name"] == "项目文档"
    assert created["description"] == "研发资料"
    assert created["status"] == "active"
    assert "created_at" in created
    assert "updated_at" in created

    assert list_response.status_code == 200
    assert list_response.json() == [created]


def test_knowledge_base_api_can_get_item_by_id():
    repository = InMemoryKnowledgeBaseRepository()

    async def override_get_knowledge_base_repository():
        return repository

    app.dependency_overrides[
        get_knowledge_base_repository
    ] = override_get_knowledge_base_repository
    try:
        client = TestClient(app)
        create_response = client.post(
            "/api/knowledge-bases",
            json={"name": "详情测试库", "description": "用于详情查询"},
        )
        created = create_response.json()

        detail_response = client.get(f"/api/knowledge-bases/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert detail_response.status_code == 200
    assert detail_response.json() == created


def test_knowledge_base_api_returns_404_when_item_is_not_visible():
    repository = InMemoryKnowledgeBaseRepository()

    async def override_get_knowledge_base_repository():
        return repository

    app.dependency_overrides[
        get_knowledge_base_repository
    ] = override_get_knowledge_base_repository
    try:
        client = TestClient(app)
        response = client.get("/api/knowledge-bases/kb_missing")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_knowledge_base_api_can_update_item_by_id():
    repository = InMemoryKnowledgeBaseRepository()

    async def override_get_knowledge_base_repository():
        return repository

    app.dependency_overrides[
        get_knowledge_base_repository
    ] = override_get_knowledge_base_repository
    try:
        client = TestClient(app)
        create_response = client.post(
            "/api/knowledge-bases",
            json={"name": "修改前", "description": "旧描述"},
        )
        created = create_response.json()

        update_response = client.put(
            f"/api/knowledge-bases/{created['id']}",
            json={"name": "修改后", "description": "新描述"},
        )
    finally:
        app.dependency_overrides.clear()

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["id"] == created["id"]
    assert updated["user_id"] == DEFAULT_USER_ID
    assert updated["name"] == "修改后"
    assert updated["description"] == "新描述"
    assert updated["status"] == "active"
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] > created["updated_at"]


def test_knowledge_base_api_returns_404_when_update_target_is_not_visible():
    repository = InMemoryKnowledgeBaseRepository()

    async def override_get_knowledge_base_repository():
        return repository

    app.dependency_overrides[
        get_knowledge_base_repository
    ] = override_get_knowledge_base_repository
    try:
        client = TestClient(app)
        response = client.put(
            "/api/knowledge-bases/kb_missing",
            json={"name": "不会创建"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_knowledge_base_api_can_hard_delete_item_by_id():
    repository = InMemoryKnowledgeBaseRepository()
    vector_service = FakeVectorService()
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()

    async def override_get_knowledge_base_repository():
        return repository

    app.dependency_overrides[
        get_knowledge_base_repository
    ] = override_get_knowledge_base_repository
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        create_response = client.post(
            "/api/knowledge-bases",
            json={"name": "准备删除", "description": "删除后列表不可见"},
        )
        created = create_response.json()
        document = make_document("doc_target", created["id"])
        document_repository.items.append(document)
        storage.objects[(document.storage_bucket, document.storage_object_key)] = {"data": b"raw"}
        storage.objects[(document.parsed_bucket, document.parsed_object_key)] = {"data": b"{}"}

        delete_response = client.delete(f"/api/knowledge-bases/{created['id']}")
        list_response = client.get("/api/knowledge-bases")
        detail_response = client.get(f"/api/knowledge-bases/{created['id']}")
    finally:
        app.dependency_overrides.clear()

    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["id"] == created["id"]
    assert deleted["user_id"] == DEFAULT_USER_ID
    assert deleted["status"] == "active"
    assert vector_service.deleted_knowledge_bases == [
        {
            "user_id": DEFAULT_USER_ID,
            "knowledge_base_id": created["id"],
        }
    ]
    assert (document.storage_bucket, document.storage_object_key) not in storage.objects
    assert (document.parsed_bucket, document.parsed_object_key) not in storage.objects
    assert list_response.status_code == 200
    assert list_response.json() == []
    assert detail_response.status_code == 404
    assert detail_response.json() == {"detail": "Knowledge base not found"}


def test_knowledge_base_api_returns_404_when_delete_target_is_not_visible():
    repository = InMemoryKnowledgeBaseRepository()
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    vector_service = FakeVectorService()

    async def override_get_knowledge_base_repository():
        return repository

    app.dependency_overrides[
        get_knowledge_base_repository
    ] = override_get_knowledge_base_repository
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    try:
        client = TestClient(app)
        response = client.delete("/api/knowledge-bases/kb_missing")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def run_async(coro):
    import asyncio

    return asyncio.run(coro)


def make_document(document_id: str, knowledge_base_id: str) -> Document:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return Document(
        id=document_id,
        user_id=DEFAULT_USER_ID,
        knowledge_base_id=knowledge_base_id,
        file_name="demo.md",
        file_type="text/markdown",
        file_size=3,
        storage_bucket="rag-documents",
        storage_object_key=(
            f"users/{DEFAULT_USER_ID}/knowledge_bases/{knowledge_base_id}/raw/"
            f"{document_id}/demo.md"
        ),
        status="embedded",
        error_message=None,
        parsed_bucket="rag-parsed-results",
        parsed_object_key=(
            f"users/{DEFAULT_USER_ID}/knowledge_bases/{knowledge_base_id}/parsed/"
            f"{document_id}.json"
        ),
        task_id=None,
        created_at=now,
        updated_at=now,
    )
