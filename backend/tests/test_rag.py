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
from app.main import app
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
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
    def embed_texts(self, texts):
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


class FakeLocalLLMService:
    async def generate_answer(self, system_prompt, user_prompt):
        return "测试标题"


class UnavailableLocalLLMService:
    async def generate_answer(self, system_prompt, user_prompt):
        raise LocalLLMUnavailableError(LOCAL_LLM_UNAVAILABLE_MESSAGE)


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
