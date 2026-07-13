from app.models.knowledge_base_config import (
    GenerationConfig,
    KnowledgeBaseConfig,
    ProcessingConfig,
    RetrievalConfig,
)
from app.services.knowledge_base_config import (
    build_default_knowledge_base_config,
    indexing_config_changed,
)
from app.services.knowledge_base_config import (
    ModelConfigurationError,
    validate_config_update_dependencies,
)
from app.schemas.knowledge_base_config import KnowledgeBaseConfigUpdate
from app.core.config import Settings
from app.api.routes.knowledge_base import (
    get_document_repository,
    get_knowledge_base_config_repository,
    get_knowledge_base_repository,
)
from app.main import app
from app.models.knowledge_base import KnowledgeBase
from datetime import datetime, timezone
from fastapi.testclient import TestClient


def make_config(
    knowledge_base_id: str,
    *,
    chunk_size: int = 500,
    top_k: int = 5,
    embedding_model_name: str = "embed-a",
) -> KnowledgeBaseConfig:
    return KnowledgeBaseConfig(
        knowledge_base_id=knowledge_base_id,
        user_id="user_a",
        processing=ProcessingConfig(chunk_size=chunk_size),
        retrieval=RetrievalConfig(top_k=top_k),
        generation=GenerationConfig(llm_model_name="llm-a"),
        version=1,
    )


def test_knowledge_base_configs_keep_processing_and_retrieval_values_isolated():
    first = make_config("kb_first", chunk_size=300, top_k=3)
    second = make_config("kb_second", chunk_size=800, top_k=8)

    assert first.knowledge_base_id != second.knowledge_base_id
    assert first.processing.chunk_size == 300
    assert second.processing.chunk_size == 800
    assert first.retrieval.top_k == 3
    assert second.retrieval.top_k == 8


def test_default_processing_config_uses_the_ui_default_separator():
    config = build_default_knowledge_base_config(
        "kb_target",
        "user_a",
        Settings(),
    )

    assert config.processing.separator == "\\n\\n"


def test_indexing_config_change_requires_reindex_but_retrieval_change_does_not():
    current = make_config("kb_target")
    changed_processing = make_config("kb_target", chunk_size=600)
    changed_retrieval = make_config("kb_target", top_k=10)

    assert indexing_config_changed(current, changed_processing) is True
    assert indexing_config_changed(current, changed_retrieval) is False


def test_config_update_rejects_a_missing_explicit_ollama_model(monkeypatch):
    config = make_config("kb_target")
    update = KnowledgeBaseConfigUpdate(
        processing={"embedding_model_name": "missing-embed"}
    )

    async def fake_fetch_model_names(_settings):
        return ["available-embed", "available-llm"]

    monkeypatch.setattr(
        "app.services.knowledge_base_config._fetch_ollama_model_names",
        fake_fetch_model_names,
    )

    import asyncio

    try:
        asyncio.run(
            validate_config_update_dependencies(
                update,
                config,
                Settings(ollama_base_url="http://ollama.test"),
            )
        )
    except ModelConfigurationError as exc:
        assert str(exc) == "Configured embedding model was not found: missing-embed"
    else:
        raise AssertionError("Expected the missing model to be rejected")


class InMemoryKnowledgeBaseRepository:
    def __init__(self, knowledge_base):
        self.knowledge_base = knowledge_base

    async def get_active_by_id_and_user(self, kb_id, user_id):
        if self.knowledge_base.id == kb_id and self.knowledge_base.user_id == user_id:
            return self.knowledge_base
        return None


class InMemoryConfigRepository:
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


class InMemoryDocumentRepository:
    def __init__(self):
        self.marked = []

    async def mark_needs_reindex_by_knowledge_base(self, user_id, knowledge_base_id, updated_at):
        self.marked.append((user_id, knowledge_base_id))
        return 1


def test_config_api_isolated_and_only_marks_documents_for_indexing_changes():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    knowledge_base = KnowledgeBase(
        id="kb_target",
        user_id="default_user",
        name="测试知识库",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    knowledge_base_repository = InMemoryKnowledgeBaseRepository(knowledge_base)
    config_repository = InMemoryConfigRepository()
    document_repository = InMemoryDocumentRepository()
    app.dependency_overrides[get_knowledge_base_repository] = lambda: knowledge_base_repository
    app.dependency_overrides[get_knowledge_base_config_repository] = lambda: config_repository
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    try:
        client = TestClient(app)
        first = client.get("/api/knowledge-bases/kb_target/config")
        retrieval_only = client.put(
            "/api/knowledge-bases/kb_target/config",
            json={"retrieval": {"top_k": 9}},
        )
        indexing = client.put(
            "/api/knowledge-bases/kb_target/config",
            json={"processing": {"chunk_size": 600}},
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert retrieval_only.status_code == 200
    assert retrieval_only.json()["retrieval"]["top_k"] == 9
    assert document_repository.marked == [("default_user", "kb_target")]
    assert indexing.status_code == 200
    assert indexing.json()["processing"]["chunk_size"] == 600
