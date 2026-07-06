from fastapi.testclient import TestClient

from app.api.routes.knowledge_base import get_knowledge_base_repository
from app.main import app
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.knowledge_base import (
    DEFAULT_USER_ID,
    create_knowledge_base,
    list_knowledge_bases,
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


def run_async(coro):
    import asyncio

    return asyncio.run(coro)
