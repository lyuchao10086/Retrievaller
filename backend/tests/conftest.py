import pytest

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.api.routes.knowledge_base import get_knowledge_base_config_repository
from app.main import app


class InMemoryKnowledgeBaseConfigRepository:
    def __init__(self):
        self.items = {}

    async def get_by_knowledge_base_and_user(self, knowledge_base_id, user_id):
        return self.items.get((knowledge_base_id, user_id))

    async def insert(self, config):
        self.items[(config.knowledge_base_id, config.user_id)] = config
        return config

    async def update(self, config):
        self.items[(config.knowledge_base_id, config.user_id)] = config
        return config


@pytest.fixture(autouse=True)
def authenticate_existing_route_tests():
    """Keep legacy endpoint tests focused on business behavior, not login setup."""
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="default_user",
        username="test-user",
    )
    app.dependency_overrides[get_knowledge_base_config_repository] = (
        InMemoryKnowledgeBaseConfigRepository
    )
    yield
    app.dependency_overrides.clear()
