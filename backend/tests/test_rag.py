from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.routes.rag import (
    get_chunk_repository,
    get_document_repository,
    get_embedding_service,
    get_knowledge_base_repository,
    get_local_llm_service,
    get_qa_record_repository,
    get_vector_service,
)
from app.api.routes.knowledge_base import get_knowledge_base_config_repository
from app.main import app
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_base_config import (
    GenerationConfig,
    KnowledgeBaseConfig,
    ProcessingConfig,
    RetrievalConfig,
)
from app.services.knowledge_base import DEFAULT_USER_ID
from app.services.local_llm_service import (
    LOCAL_LLM_UNAVAILABLE_MESSAGE,
    LocalLLMUnavailableError,
)
from app.services.rag_service import NO_MULTI_RETRIEVAL_ANSWER
from app.services.vector_service import VectorSearchResult


class InMemoryKnowledgeBaseRepository:
    def __init__(self, items=None):
        self.items = items or []

    async def list_active_by_ids_and_user(self, kb_ids, user_id):
        return [
            item
            for item in self.items
            if item.id in kb_ids and item.user_id == user_id and item.status == "active"
        ]


class FakeChunkRepository:
    def __init__(self, has_embedded=False, chunks=None):
        self.has_embedded = has_embedded
        self.chunks = chunks or []

    async def exists_embedded_by_knowledge_base_ids(self, user_id, knowledge_base_ids):
        return self.has_embedded

    async def list_by_ids_and_knowledge_base_ids(self, user_id, knowledge_base_ids, chunk_ids):
        return [
            chunk
            for chunk in self.chunks
            if chunk.id in chunk_ids
            and chunk.knowledge_base_id in knowledge_base_ids
            and chunk.user_id == user_id
        ]

    async def list_by_ids(self, user_id, knowledge_base_id, chunk_ids):
        return [
            chunk
            for chunk in self.chunks
            if chunk.id in chunk_ids
            and chunk.knowledge_base_id == knowledge_base_id
            and chunk.user_id == user_id
        ]


class FakeDocumentRepository:
    def __init__(self, documents=None):
        self.documents = documents or []

    async def list_by_ids_and_knowledge_base_ids(self, user_id, knowledge_base_ids, document_ids):
        return [
            document
            for document in self.documents
            if document.id in document_ids
            and document.knowledge_base_id in knowledge_base_ids
            and document.user_id == user_id
        ]

    async def list_by_ids_and_knowledge_base(self, user_id, knowledge_base_id, document_ids):
        return [
            document
            for document in self.documents
            if document.id in document_ids
            and document.knowledge_base_id == knowledge_base_id
            and document.user_id == user_id
        ]


class FakeQaRecordRepository:
    def __init__(self):
        self.items = []

    async def insert(self, record):
        self.items.append(record)
        return record

    async def list_recent_by_user(self, user_id, limit=50):
        return [item for item in self.items if item.user_id == user_id][:limit]

    async def get_by_id_and_user(self, qa_record_id, user_id):
        return next(
            (item for item in self.items if item.id == qa_record_id and item.user_id == user_id),
            None,
        )

    async def delete_by_id_and_user(self, qa_record_id, user_id):
        return None


class FakeEmbeddingService:
    def __init__(self):
        self.model_names = []

    def embed_texts(self, texts, model_name=None):
        self.model_names.append(model_name)
        return [[0.1, 0.2, 0.3] for _ in texts]


class FakeVectorService:
    def __init__(self, hits=None):
        self.hits = hits or []

    def search_chunk_embeddings_in_knowledge_bases(
        self,
        query_embedding,
        user_id,
        knowledge_base_ids,
        top_k,
    ):
        return self.hits[:top_k]

    def search_chunk_embeddings(
        self,
        query_embedding,
        user_id,
        knowledge_base_id,
        top_k,
    ):
        return [
            hit
            for hit in self.hits
            if hit.knowledge_base_id == knowledge_base_id
        ][:top_k]


class FakeLocalLLMService:
    async def generate_answer(self, system_prompt, user_prompt, **_options):
        return "测试标题"


class UnavailableLocalLLMService:
    async def generate_answer(self, system_prompt, user_prompt, **_options):
        raise LocalLLMUnavailableError(LOCAL_LLM_UNAVAILABLE_MESSAGE)


class RecordingLocalLLMService:
    def __init__(self):
        self.calls = []

    async def generate_answer(self, system_prompt, user_prompt, **options):
        self.calls.append(options)
        return "测试回答"


class InMemoryKnowledgeBaseConfigRepository:
    def __init__(self, configs):
        self.configs = {
            (config.knowledge_base_id, config.user_id): config for config in configs
        }

    async def get_by_knowledge_base_and_user(self, knowledge_base_id, user_id):
        return self.configs.get((knowledge_base_id, user_id))

    async def insert(self, config):
        self.configs[(config.knowledge_base_id, config.user_id)] = config
        return config

    async def update(self, config):
        self.configs[(config.knowledge_base_id, config.user_id)] = config
        return config


def test_multi_rag_answer_returns_no_retrieval_message_without_embedded_chunks():
    qa_repository = FakeQaRecordRepository()

    app.dependency_overrides[get_knowledge_base_repository] = lambda: InMemoryKnowledgeBaseRepository(
        [make_knowledge_base("kb_target")]
    )
    app.dependency_overrides[get_chunk_repository] = lambda: FakeChunkRepository(has_embedded=False)
    app.dependency_overrides[get_document_repository] = lambda: FakeDocumentRepository()
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_service] = lambda: FakeVectorService()
    app.dependency_overrides[get_local_llm_service] = lambda: FakeLocalLLMService()
    app.dependency_overrides[get_qa_record_repository] = lambda: qa_repository
    try:
        response = TestClient(app).post(
            "/api/rag/answer",
            json={
                "query": "这个知识库讲了什么？",
                "knowledge_base_ids": ["kb_target"],
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == NO_MULTI_RETRIEVAL_ANSWER
    assert body["sources"] == []
    assert body["qa_record_id"] == qa_repository.items[0].id
    assert qa_repository.items[0].answer == NO_MULTI_RETRIEVAL_ANSWER


def test_multi_rag_answer_returns_404_for_invalid_knowledge_base_ids():
    app.dependency_overrides[get_knowledge_base_repository] = lambda: InMemoryKnowledgeBaseRepository(
        [make_knowledge_base("kb_valid")]
    )
    app.dependency_overrides[get_chunk_repository] = lambda: FakeChunkRepository(has_embedded=False)
    app.dependency_overrides[get_document_repository] = lambda: FakeDocumentRepository()
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_service] = lambda: FakeVectorService()
    app.dependency_overrides[get_local_llm_service] = lambda: FakeLocalLLMService()
    app.dependency_overrides[get_qa_record_repository] = lambda: FakeQaRecordRepository()
    try:
        response = TestClient(app).post(
            "/api/rag/answer",
            json={
                "query": "问题",
                "knowledge_base_ids": ["kb_valid", "kb_missing"],
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "message": "Invalid knowledge_base_ids",
        "invalid_knowledge_base_ids": ["kb_missing"],
    }


def test_multi_rag_answer_returns_503_when_local_llm_is_unavailable():
    chunk = make_chunk("chunk_target", "doc_target", "kb_target")
    document = make_document("doc_target", "kb_target")
    vector_hit = VectorSearchResult(
        chunk_id=chunk.id,
        document_id=document.id,
        knowledge_base_id="kb_target",
        user_id=DEFAULT_USER_ID,
        score=0.91,
    )

    app.dependency_overrides[get_knowledge_base_repository] = lambda: InMemoryKnowledgeBaseRepository(
        [make_knowledge_base("kb_target")]
    )
    app.dependency_overrides[get_chunk_repository] = lambda: FakeChunkRepository(
        has_embedded=True,
        chunks=[chunk],
    )
    app.dependency_overrides[get_document_repository] = lambda: FakeDocumentRepository([document])
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_service] = lambda: FakeVectorService([vector_hit])
    app.dependency_overrides[get_local_llm_service] = lambda: UnavailableLocalLLMService()
    app.dependency_overrides[get_qa_record_repository] = lambda: FakeQaRecordRepository()
    try:
        response = TestClient(app).post(
            "/api/rag/answer",
            json={
                "query": "问题",
                "knowledge_base_ids": ["kb_target"],
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": LOCAL_LLM_UNAVAILABLE_MESSAGE}


def test_multi_rag_answer_ignores_milvus_hit_when_document_is_not_embedded():
    chunk = make_chunk("chunk_target", "doc_target", "kb_target")
    vector_hit = VectorSearchResult(
        chunk_id=chunk.id,
        document_id="doc_target",
        knowledge_base_id="kb_target",
        user_id=DEFAULT_USER_ID,
        score=0.91,
    )

    app.dependency_overrides[get_knowledge_base_repository] = lambda: InMemoryKnowledgeBaseRepository(
        [make_knowledge_base("kb_target")]
    )
    app.dependency_overrides[get_chunk_repository] = lambda: FakeChunkRepository(
        has_embedded=True,
        chunks=[chunk],
    )
    app.dependency_overrides[get_document_repository] = lambda: FakeDocumentRepository()
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_service] = lambda: FakeVectorService([vector_hit])
    app.dependency_overrides[get_local_llm_service] = lambda: FakeLocalLLMService()
    app.dependency_overrides[get_qa_record_repository] = lambda: FakeQaRecordRepository()
    try:
        response = TestClient(app).post(
            "/api/rag/answer",
            json={
                "query": "问题",
                "knowledge_base_ids": ["kb_target"],
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["answer"] == NO_MULTI_RETRIEVAL_ANSWER
    assert response.json()["sources"] == []


def test_multi_rag_answer_uses_selected_knowledge_base_config():
    knowledge_base = make_knowledge_base("kb_configured")
    first_chunk = make_chunk("chunk_first", "doc_target", knowledge_base.id)
    second_chunk = make_chunk("chunk_second", "doc_target", knowledge_base.id)
    document = make_document("doc_target", knowledge_base.id)
    vector_hits = [
        VectorSearchResult(
            chunk_id=first_chunk.id,
            document_id=document.id,
            knowledge_base_id=knowledge_base.id,
            user_id=DEFAULT_USER_ID,
            score=0.92,
        ),
        VectorSearchResult(
            chunk_id=second_chunk.id,
            document_id=document.id,
            knowledge_base_id=knowledge_base.id,
            user_id=DEFAULT_USER_ID,
            score=0.82,
        ),
    ]
    config_repository = InMemoryKnowledgeBaseConfigRepository(
        [
            KnowledgeBaseConfig(
                knowledge_base_id=knowledge_base.id,
                user_id=DEFAULT_USER_ID,
                processing=ProcessingConfig(embedding_model_name="embed-configured"),
                retrieval=RetrievalConfig(top_k=1, similarity_threshold=0.5),
                generation=GenerationConfig(
                    llm_model_name="llm-configured",
                    temperature=0.7,
                    max_tokens=321,
                ),
            )
        ]
    )
    embedding_service = FakeEmbeddingService()
    llm_service = RecordingLocalLLMService()

    app.dependency_overrides[get_knowledge_base_repository] = lambda: InMemoryKnowledgeBaseRepository(
        [knowledge_base]
    )
    app.dependency_overrides[get_chunk_repository] = lambda: FakeChunkRepository(
        has_embedded=True,
        chunks=[first_chunk, second_chunk],
    )
    app.dependency_overrides[get_document_repository] = lambda: FakeDocumentRepository([document])
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_service] = lambda: FakeVectorService(vector_hits)
    app.dependency_overrides[get_local_llm_service] = lambda: llm_service
    app.dependency_overrides[get_qa_record_repository] = lambda: FakeQaRecordRepository()
    app.dependency_overrides[get_knowledge_base_config_repository] = lambda: config_repository
    try:
        response = TestClient(app).post(
            "/api/rag/answer",
            json={
                "query": "配置是否生效？",
                "knowledge_base_ids": [knowledge_base.id],
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [source["chunk_id"] for source in response.json()["sources"]] == [first_chunk.id]
    assert embedding_service.model_names == ["embed-configured"]
    assert llm_service.calls[0] == {
        "model_name": "llm-configured",
        "temperature": 0.7,
        "max_tokens": 321,
    }


def test_multi_rag_answer_rejects_mismatched_generation_configs():
    first_knowledge_base = make_knowledge_base("kb_first")
    second_knowledge_base = make_knowledge_base("kb_second")
    config_repository = InMemoryKnowledgeBaseConfigRepository(
        [
            KnowledgeBaseConfig(
                knowledge_base_id=first_knowledge_base.id,
                user_id=DEFAULT_USER_ID,
                generation=GenerationConfig(
                    llm_model_name="llm-first",
                    temperature=0.2,
                    max_tokens=1024,
                ),
            ),
            KnowledgeBaseConfig(
                knowledge_base_id=second_knowledge_base.id,
                user_id=DEFAULT_USER_ID,
                generation=GenerationConfig(
                    llm_model_name="llm-second",
                    temperature=0.2,
                    max_tokens=1024,
                ),
            ),
        ]
    )

    app.dependency_overrides[get_knowledge_base_repository] = lambda: InMemoryKnowledgeBaseRepository(
        [first_knowledge_base, second_knowledge_base]
    )
    app.dependency_overrides[get_chunk_repository] = lambda: FakeChunkRepository(
        has_embedded=False
    )
    app.dependency_overrides[get_document_repository] = FakeDocumentRepository
    app.dependency_overrides[get_embedding_service] = FakeEmbeddingService
    app.dependency_overrides[get_vector_service] = FakeVectorService
    app.dependency_overrides[get_local_llm_service] = FakeLocalLLMService
    app.dependency_overrides[get_qa_record_repository] = FakeQaRecordRepository
    app.dependency_overrides[get_knowledge_base_config_repository] = lambda: config_repository
    try:
        response = TestClient(app).post(
            "/api/rag/answer",
            json={
                "query": "配置不一致时应该怎样处理？",
                "knowledge_base_ids": [
                    first_knowledge_base.id,
                    second_knowledge_base.id,
                ],
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Selected knowledge bases use different generation settings. "
            "Select one knowledge base or align their LLM configuration."
        )
    }


def make_knowledge_base(kb_id: str) -> KnowledgeBase:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return KnowledgeBase(
        id=kb_id,
        user_id=DEFAULT_USER_ID,
        name=f"{kb_id} 名称",
        description=None,
        status="active",
        created_at=now,
        updated_at=now,
    )


def make_chunk(chunk_id: str, document_id: str, knowledge_base_id: str) -> Chunk:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return Chunk(
        id=chunk_id,
        user_id=DEFAULT_USER_ID,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        chunk_index=0,
        title=None,
        content="用于测试的 chunk 内容",
        chapter=None,
        section=None,
        subsection=None,
        status="embedded",
        vector_id="vec_target",
        created_at=now,
        updated_at=now,
    )


def make_document(document_id: str, knowledge_base_id: str) -> Document:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return Document(
        id=document_id,
        user_id=DEFAULT_USER_ID,
        knowledge_base_id=knowledge_base_id,
        file_name="测试文档.md",
        file_type="md",
        file_size=100,
        storage_bucket="bucket",
        storage_object_key="object",
        status="embedded",
        error_message=None,
        parsed_bucket=None,
        parsed_object_key=None,
        task_id=None,
        created_at=now,
        updated_at=now,
    )
