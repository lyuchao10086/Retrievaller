from datetime import timedelta

from fastapi.testclient import TestClient

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.api.routes.auth import get_user_repository
from app.api.routes.knowledge_base import get_knowledge_base_repository
from app.core.security import create_access_token
from app.main import app
from app.models.knowledge_base import KnowledgeBase


class InMemoryKnowledgeBaseRepository:
    def __init__(self, items):
        self.items = items

    async def list_active_by_user(self, user_id):
        return [item for item in self.items if item.user_id == user_id and item.status == "active"]

    async def get_active_by_id_and_user(self, kb_id, user_id):
        return next(
            (
                item
                for item in self.items
                if item.id == kb_id and item.user_id == user_id and item.status == "active"
            ),
            None,
        )


class InMemoryUserRepository:
    def __init__(self):
        self.items = []

    async def get_by_username(self, username):
        return next((item for item in self.items if item.username == username), None)

    async def get_by_id(self, user_id):
        return next((item for item in self.items if item.id == user_id), None)

    async def insert(self, user):
        self.items.append(user)
        return user


def test_register_then_login_returns_a_user_session_without_database():
    repository = InMemoryUserRepository()
    app.dependency_overrides[get_user_repository] = lambda: repository
    try:
        client = TestClient(app)
        registration = client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "valid-password"},
        )
        login = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "valid-password"},
        )
    finally:
        app.dependency_overrides.clear()

    assert registration.status_code == 201
    assert login.status_code == 200
    registered = registration.json()
    logged_in = login.json()
    assert registered["user_id"] == logged_in["user_id"]
    assert registered["username"] == logged_in["username"] == "alice"
    assert isinstance(registered["access_token"], str)
    assert isinstance(logged_in["access_token"], str)
    assert registered["expires_in"] > 0


def test_knowledge_base_api_requires_bearer_token():
    app.dependency_overrides.clear()
    try:
        response = TestClient(app).get("/api/knowledge-bases")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_current_user_only_lists_own_knowledge_bases():
    repository = InMemoryKnowledgeBaseRepository([
        make_knowledge_base("kb_alice", "user_alice"),
        make_knowledge_base("kb_bob", "user_bob"),
    ])
    app.dependency_overrides[get_current_user] = lambda: CurrentUser("user_alice", "alice")
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    try:
        response = TestClient(app).get("/api/knowledge-bases")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["kb_alice"]


def test_cross_user_knowledge_base_detail_is_not_visible():
    repository = InMemoryKnowledgeBaseRepository([
        make_knowledge_base("kb_bob", "user_bob"),
    ])
    app.dependency_overrides[get_current_user] = lambda: CurrentUser("user_alice", "alice")
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    try:
        response = TestClient(app).get("/api/knowledge-bases/kb_bob")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_expired_bearer_token_is_rejected():
    expired_token = create_access_token(
        user_id="user_alice",
        username="alice",
        expires_delta=timedelta(seconds=-1),
    )
    app.dependency_overrides.clear()
    try:
        response = TestClient(app).get(
            "/api/knowledge-bases",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Token has expired"}


def test_malformed_bearer_token_is_rejected():
    app.dependency_overrides.clear()
    try:
        response = TestClient(app).get(
            "/api/knowledge-bases",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token"}


def make_knowledge_base(kb_id, user_id):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return KnowledgeBase(
        id=kb_id,
        user_id=user_id,
        name=kb_id,
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )
