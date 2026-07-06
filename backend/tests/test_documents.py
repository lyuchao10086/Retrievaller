import json
from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient

from app.api.routes.document import (
    get_chunk_repository,
    get_document_repository,
    get_document_storage,
    get_embedding_service,
    get_knowledge_base_repository,
    get_parse_task_dispatcher,
    get_vector_service,
)
from app.main import app
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.services.chunk import (
    CHUNKS_ALREADY_EXIST_MESSAGE,
    DOCUMENT_MUST_BE_CHUNKED_MESSAGE,
    DOCUMENT_MUST_BE_PARSED_MESSAGE,
    NO_CHUNKS_AVAILABLE_FOR_EMBEDDING_MESSAGE,
    create_chunks_from_parsed_document,
    embed_document_chunks,
    get_document_embedding_status,
    list_chunks_by_document,
)
from app.services.document import (
    DEFAULT_DOCUMENT_BUCKET,
    PARSED_STATUS,
    PARSING_STATUS,
    UPLOADED_STATUS,
    delete_document,
    get_document_by_id,
    get_parsed_document_content,
    list_documents_by_knowledge_base,
    parse_document,
    upload_document_to_knowledge_base,
)
from app.services.document import DocumentStatusError
from app.services.document_parse_processor import (
    PARSED_RESULTS_BUCKET,
    UNSUPPORTED_FILE_TYPE_MESSAGE,
    process_document_parse,
)
from app.services.embedding_service import OllamaEmbeddingService
from app.services.parsers.markdown_parser import parse_markdown_document
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


class InMemoryChunkRepository:
    def __init__(self):
        self.items = []

    async def insert_many(self, chunks):
        self.items.extend(chunks)
        return chunks

    async def list_by_document(self, user_id, knowledge_base_id, document_id):
        return sorted(
            [
                item
                for item in self.items
                if item.user_id == user_id
                and item.knowledge_base_id == knowledge_base_id
                and item.document_id == document_id
            ],
            key=lambda item: item.chunk_index,
        )

    async def exists_by_document(self, user_id, knowledge_base_id, document_id):
        return bool(
            await self.list_by_document(user_id, knowledge_base_id, document_id)
        )

    async def list_pending_for_embedding(self, user_id, knowledge_base_id, document_id):
        return [
            item
            for item in await self.list_by_document(
                user_id,
                knowledge_base_id,
                document_id,
            )
            if item.status == "created" and item.vector_id is None
        ]

    async def update_embedding_result(self, user_id, knowledge_base_id, chunk_id, vector_id, updated_at):
        for item in self.items:
            if (
                item.user_id == user_id
                and item.knowledge_base_id == knowledge_base_id
                and item.id == chunk_id
            ):
                item.vector_id = vector_id
                item.status = "embedded"
                item.updated_at = updated_at
                return item
        return None

    async def count_embedding_status(self, user_id, knowledge_base_id, document_id):
        chunks = await self.list_by_document(user_id, knowledge_base_id, document_id)
        embedded_chunks = len(
            [
                item
                for item in chunks
                if item.status == "embedded" and item.vector_id is not None
            ]
        )
        return {
            "total_chunks": len(chunks),
            "embedded_chunks": embedded_chunks,
            "pending_chunks": len(chunks) - embedded_chunks,
        }


class FakeEmbeddingService:
    def __init__(self):
        self.texts = []

    def embed_texts(self, texts):
        self.texts.extend(texts)
        return [[float(index), 0.0, 1.0] for index, _ in enumerate(texts)]


class FakeVectorService:
    def __init__(self):
        self.calls = []

    def insert_chunk_embeddings(self, chunks, embeddings):
        self.calls.append(
            {
                "chunk_ids": [chunk.id for chunk in chunks],
                "embeddings": embeddings,
            }
        )
        return [f"vector_{chunk.id}" for chunk in chunks]


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


def test_get_parsed_document_content_reads_json_from_storage():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_parsed", knowledge_base.id, DEFAULT_USER_ID)
    document.status = PARSED_STATUS
    document.parsed_bucket = "rag-parsed-results"
    document.parsed_object_key = (
        f"users/{DEFAULT_USER_ID}/knowledge_bases/{knowledge_base.id}"
        f"/parsed/{document.id}.json"
    )
    parsed_json = {
        "document_id": document.id,
        "knowledge_base_id": knowledge_base.id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "parser": "markdown",
        "sections": [{"level": 1, "title": "标题", "content": "正文"}],
    }
    storage.objects[(document.parsed_bucket, document.parsed_object_key)] = {
        "data": json.dumps(parsed_json, ensure_ascii=False).encode("utf-8"),
        "content_type": "application/json",
    }
    document_repository.items.append(document)

    content = run_async(
        get_parsed_document_content(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            storage=storage,
            kb_id=knowledge_base.id,
            document_id=document.id,
        )
    )

    assert content == parsed_json


def test_create_chunks_from_parsed_document_saves_section_chunks():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_parsed_document("doc_parsed", knowledge_base.id)
    parsed_json = {
        "sections": [
            {
                "title": "第一章",
                "content": "总览内容",
                "chapter": "第一章",
                "section": None,
                "subsection": None,
            },
            {
                "title": "空章节",
                "content": "",
                "chapter": "第一章",
                "section": "空章节",
                "subsection": None,
            },
            {
                "title": "第一节",
                "content": "章节内容",
                "chapter": "第一章",
                "section": "第一节",
                "subsection": None,
            },
        ]
    }
    storage.objects[(document.parsed_bucket, document.parsed_object_key)] = {
        "data": json.dumps(parsed_json, ensure_ascii=False).encode("utf-8"),
        "content_type": "application/json",
    }
    document_repository.items.append(document)

    chunks = run_async(
        create_chunks_from_parsed_document(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            kb_id=knowledge_base.id,
            document_id=document.id,
        )
    )

    assert len(chunks) == 2
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert chunks[0].title == "第一章"
    assert chunks[0].content == "总览内容"
    assert chunks[0].chapter == "第一章"
    assert chunks[0].section is None
    assert chunks[0].subsection is None
    assert chunks[0].status == "created"
    assert chunks[0].vector_id is None
    assert chunks[1].title == "第一节"
    assert chunks[1].content == "章节内容"
    assert document.status == "chunked"
    assert document_repository.status_updates == ["chunked"]


def test_create_chunks_from_parsed_document_rejects_existing_chunks():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_parsed_document("doc_parsed", knowledge_base.id)
    document_repository.items.append(document)
    chunk_repository.items.append(make_chunk("chunk_existing", document, 0))

    try:
        run_async(
            create_chunks_from_parsed_document(
                knowledge_base_repository=knowledge_base_repository,
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                storage=storage,
                kb_id=knowledge_base.id,
                document_id=document.id,
            )
        )
    except ValueError as exc:
        error = exc
    else:
        error = None

    assert error is not None
    assert str(error) == CHUNKS_ALREADY_EXIST_MESSAGE


def test_embed_document_chunks_writes_vectors_and_updates_status():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    embedding_service = FakeEmbeddingService()
    vector_service = FakeVectorService()
    document = make_parsed_document("doc_chunked", knowledge_base.id)
    document.status = "chunked"
    document_repository.items.append(document)
    chunk_repository.items.extend(
        [
            make_chunk("chunk_0", document, 0),
            make_chunk("chunk_1", document, 1),
        ]
    )

    embedded_chunks = run_async(
        embed_document_chunks(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            embedding_service=embedding_service,
            vector_service=vector_service,
            kb_id=knowledge_base.id,
            document_id=document.id,
        )
    )

    assert [chunk.status for chunk in embedded_chunks] == ["embedded", "embedded"]
    assert [chunk.vector_id for chunk in embedded_chunks] == [
        "vector_chunk_0",
        "vector_chunk_1",
    ]
    assert embedding_service.texts == ["content 0", "content 1"]
    assert vector_service.calls == [
        {
            "chunk_ids": ["chunk_0", "chunk_1"],
            "embeddings": [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]],
        }
    ]
    assert document.status == "embedded"
    assert document_repository.status_updates == ["embedded"]


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


def test_embed_document_chunks_requires_chunked_document():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    document = make_parsed_document("doc_parsed", knowledge_base.id)
    document_repository.items.append(document)

    try:
        run_async(
            embed_document_chunks(
                knowledge_base_repository=knowledge_base_repository,
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                embedding_service=FakeEmbeddingService(),
                vector_service=FakeVectorService(),
                kb_id=knowledge_base.id,
                document_id=document.id,
            )
        )
    except ValueError as exc:
        error = exc
    else:
        error = None

    assert error is not None
    assert str(error) == DOCUMENT_MUST_BE_CHUNKED_MESSAGE


def test_embed_document_chunks_requires_pending_chunks():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    document = make_parsed_document("doc_chunked", knowledge_base.id)
    document.status = "chunked"
    document_repository.items.append(document)

    try:
        run_async(
            embed_document_chunks(
                knowledge_base_repository=knowledge_base_repository,
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                embedding_service=FakeEmbeddingService(),
                vector_service=FakeVectorService(),
                kb_id=knowledge_base.id,
                document_id=document.id,
            )
        )
    except ValueError as exc:
        error = exc
    else:
        error = None

    assert error is not None
    assert str(error) == NO_CHUNKS_AVAILABLE_FOR_EMBEDDING_MESSAGE


def test_get_document_embedding_status_counts_chunks():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    document = make_parsed_document("doc_chunked", knowledge_base.id)
    document.status = "chunked"
    document_repository.items.append(document)
    embedded_chunk = make_chunk("chunk_0", document, 0)
    embedded_chunk.status = "embedded"
    embedded_chunk.vector_id = "vector_chunk_0"
    pending_chunk = make_chunk("chunk_1", document, 1)
    chunk_repository.items.extend([embedded_chunk, pending_chunk])

    status_payload = run_async(
        get_document_embedding_status(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            kb_id=knowledge_base.id,
            document_id=document.id,
        )
    )

    assert status_payload == {
        "document_id": document.id,
        "status": "chunked",
        "total_chunks": 2,
        "embedded_chunks": 1,
        "pending_chunks": 1,
    }


def test_create_chunks_from_parsed_document_requires_parsed_document():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_uploaded", knowledge_base.id, DEFAULT_USER_ID)
    document_repository.items.append(document)

    try:
        run_async(
            create_chunks_from_parsed_document(
                knowledge_base_repository=knowledge_base_repository,
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                storage=storage,
                kb_id=knowledge_base.id,
                document_id=document.id,
            )
        )
    except ValueError as exc:
        error = exc
    else:
        error = None

    assert error is not None
    assert str(error) == DOCUMENT_MUST_BE_PARSED_MESSAGE


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


def test_markdown_parser_extracts_heading_hierarchy():
    markdown_text = """# 第一章
总览内容

## 第一节
章节内容

### 小节 A
小节内容

#### 细分主题
细分内容
"""

    parsed = parse_markdown_document(
        markdown_text,
        document_id="doc_md",
        knowledge_base_id="kb_md",
        file_name="guide.md",
        file_type="text/markdown",
    )

    assert parsed["document_id"] == "doc_md"
    assert parsed["knowledge_base_id"] == "kb_md"
    assert parsed["file_name"] == "guide.md"
    assert parsed["file_type"] == "text/markdown"
    assert parsed["parser"] == "markdown"
    assert parsed["sections"] == [
        {
            "level": 1,
            "title": "第一章",
            "content": "总览内容",
            "chapter": "第一章",
            "section": None,
            "subsection": None,
        },
        {
            "level": 2,
            "title": "第一节",
            "content": "章节内容",
            "chapter": "第一章",
            "section": "第一节",
            "subsection": None,
        },
        {
            "level": 3,
            "title": "小节 A",
            "content": "小节内容",
            "chapter": "第一章",
            "section": "第一节",
            "subsection": "小节 A",
        },
        {
            "level": 4,
            "title": "细分主题",
            "content": "细分内容",
            "chapter": "第一章",
            "section": "第一节",
            "subsection": "细分主题",
        },
    ]


def test_process_document_parse_saves_markdown_result_to_storage():
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_md", "kb_md", DEFAULT_USER_ID)
    document.file_name = "guide.md"
    document.file_type = "text/markdown"
    document.storage_object_key = (
        f"users/{DEFAULT_USER_ID}/knowledge_bases/kb_md/raw/doc_md/guide.md"
    )
    storage.objects[(document.storage_bucket, document.storage_object_key)] = {
        "data": b"# Chapter\n\nBody text\n",
        "content_type": "text/markdown",
    }
    document_repository.items.append(document)

    parsed = run_async(
        process_document_parse(
            document_repository=document_repository,
            storage=storage,
            kb_id="kb_md",
            document_id="doc_md",
            user_id=DEFAULT_USER_ID,
        )
    )

    assert parsed is not None
    assert parsed.status == PARSED_STATUS
    assert parsed.error_message is None
    assert parsed.parsed_bucket == PARSED_RESULTS_BUCKET
    assert parsed.parsed_object_key == (
        f"users/{DEFAULT_USER_ID}/knowledge_bases/kb_md/parsed/doc_md.json"
    )
    saved_object = storage.objects[
        (parsed.parsed_bucket, parsed.parsed_object_key)
    ]
    saved_json = json.loads(saved_object["data"].decode("utf-8"))
    assert saved_object["content_type"] == "application/json"
    assert saved_json["parser"] == "markdown"
    assert saved_json["sections"][0]["chapter"] == "Chapter"
    assert saved_json["sections"][0]["content"] == "Body text"
    assert document_repository.status_updates == [PARSING_STATUS, PARSED_STATUS]


def test_process_document_parse_marks_non_markdown_as_failed():
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_txt", "kb_md", DEFAULT_USER_ID)
    document.file_name = "notes.txt"
    document_repository.items.append(document)

    parsed = run_async(
        process_document_parse(
            document_repository=document_repository,
            storage=storage,
            kb_id="kb_md",
            document_id="doc_txt",
            user_id=DEFAULT_USER_ID,
        )
    )

    assert parsed is not None
    assert parsed.status == "failed"
    assert parsed.error_message == UNSUPPORTED_FILE_TYPE_MESSAGE
    assert parsed.parsed_bucket is None
    assert parsed.parsed_object_key is None
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


def test_document_api_can_preview_parsed_document_content():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_parsed", knowledge_base.id, DEFAULT_USER_ID)
    document.status = PARSED_STATUS
    document.parsed_bucket = "rag-parsed-results"
    document.parsed_object_key = (
        f"users/{DEFAULT_USER_ID}/knowledge_bases/{knowledge_base.id}"
        f"/parsed/{document.id}.json"
    )
    parsed_json = {
        "document_id": document.id,
        "knowledge_base_id": knowledge_base.id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "parser": "markdown",
        "sections": [{"level": 1, "title": "标题", "content": "正文"}],
    }
    storage.objects[(document.parsed_bucket, document.parsed_object_key)] = {
        "data": json.dumps(parsed_json, ensure_ascii=False).encode("utf-8"),
        "content_type": "application/json",
    }
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/parsed"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == parsed_json


def test_document_api_can_create_and_list_chunks():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_parsed_document("doc_parsed", knowledge_base.id)
    storage.objects[(document.parsed_bucket, document.parsed_object_key)] = {
        "data": json.dumps(
            {
                "sections": [
                    {
                        "title": "第一章",
                        "content": "总览内容",
                        "chapter": "第一章",
                        "section": None,
                        "subsection": None,
                    }
                ]
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        "content_type": "application/json",
    }
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        create_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/chunks"
        )
        list_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/chunks"
        )
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 201
    created_chunks = create_response.json()
    assert len(created_chunks) == 1
    assert created_chunks[0]["user_id"] == DEFAULT_USER_ID
    assert created_chunks[0]["knowledge_base_id"] == knowledge_base.id
    assert created_chunks[0]["document_id"] == document.id
    assert created_chunks[0]["chunk_index"] == 0
    assert created_chunks[0]["title"] == "第一章"
    assert created_chunks[0]["content"] == "总览内容"
    assert created_chunks[0]["status"] == "created"
    assert created_chunks[0]["vector_id"] is None
    assert document.status == "chunked"

    assert list_response.status_code == 200
    assert list_response.json() == created_chunks


def test_document_api_returns_400_when_chunks_already_exist():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_parsed_document("doc_parsed", knowledge_base.id)
    document_repository.items.append(document)
    chunk_repository.items.append(make_chunk("chunk_existing", document, 0))

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/chunks"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": CHUNKS_ALREADY_EXIST_MESSAGE}


def test_document_api_returns_400_when_chunking_unparsed_document():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_uploaded", knowledge_base.id, DEFAULT_USER_ID)
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/chunks"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": DOCUMENT_MUST_BE_PARSED_MESSAGE}


def test_document_api_returns_404_when_chunk_document_is_not_visible():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document_repository.items.append(
        make_parsed_document("doc_target", "kb_other")
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/doc_target/chunks"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


def test_document_api_lists_chunks_for_document_ordered_by_index():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_parsed_document("doc_parsed", knowledge_base.id)
    document_repository.items.append(document)
    chunk_repository.items.extend(
        [
            make_chunk("chunk_2", document, 2),
            make_chunk("chunk_0", document, 0),
        ]
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/chunks"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [chunk["chunk_index"] for chunk in response.json()] == [0, 2]


def test_document_api_can_embed_document_chunks():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    embedding_service = FakeEmbeddingService()
    vector_service = FakeVectorService()
    document = make_parsed_document("doc_chunked", knowledge_base.id)
    document.status = "chunked"
    document_repository.items.append(document)
    chunk_repository.items.extend(
        [
            make_chunk("chunk_0", document, 0),
            make_chunk("chunk_1", document, 1),
        ]
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/embed"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "document_id": document.id,
        "status": "embedded",
        "total_chunks": 2,
        "embedded_chunks": 2,
        "pending_chunks": 0,
    }
    assert [chunk.status for chunk in chunk_repository.items] == [
        "embedded",
        "embedded",
    ]
    assert [chunk.vector_id for chunk in chunk_repository.items] == [
        "vector_chunk_0",
        "vector_chunk_1",
    ]
    assert document.status == "embedded"


def test_document_api_returns_400_when_embedding_unready_document():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    document = make_parsed_document("doc_parsed", knowledge_base.id)
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_service] = lambda: FakeVectorService()
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/embed"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": DOCUMENT_MUST_BE_CHUNKED_MESSAGE}


def test_document_api_returns_400_when_no_chunks_can_be_embedded():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    document = make_parsed_document("doc_chunked", knowledge_base.id)
    document.status = "chunked"
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_service] = lambda: FakeVectorService()
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/embed"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": NO_CHUNKS_AVAILABLE_FOR_EMBEDDING_MESSAGE}


def test_document_api_returns_404_when_embedding_document_is_not_visible():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    document_repository.items.append(make_parsed_document("doc_target", "kb_other"))

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    app.dependency_overrides[get_vector_service] = lambda: FakeVectorService()
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/doc_target/embed"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


def test_document_api_can_get_embedding_status():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    document = make_parsed_document("doc_chunked", knowledge_base.id)
    document.status = "chunked"
    document_repository.items.append(document)
    embedded_chunk = make_chunk("chunk_0", document, 0)
    embedded_chunk.status = "embedded"
    embedded_chunk.vector_id = "vector_chunk_0"
    pending_chunk = make_chunk("chunk_1", document, 1)
    chunk_repository.items.extend([embedded_chunk, pending_chunk])

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/embedding-status"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "document_id": document.id,
        "status": "chunked",
        "total_chunks": 2,
        "embedded_chunks": 1,
        "pending_chunks": 1,
    }


def test_document_api_returns_400_when_preview_document_is_not_parsed():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_uploaded", knowledge_base.id, DEFAULT_USER_ID)
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/parsed"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": "Document has not been parsed yet"}


def test_document_api_returns_400_when_preview_result_location_is_missing():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_parsed", knowledge_base.id, DEFAULT_USER_ID)
    document.status = PARSED_STATUS
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/parsed"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": "Parsed result not found"}


def test_document_api_returns_404_when_preview_knowledge_base_is_missing():
    knowledge_base_repository = InMemoryKnowledgeBaseRepository()
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    document_repository.items.append(
        make_document("doc_target", "kb_missing", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.get(
            "/api/knowledge-bases/kb_missing/documents/doc_target/parsed"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_document_api_returns_404_when_preview_document_is_not_visible():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    document_repository.items.append(
        make_document("doc_target", "kb_other", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/doc_target/parsed"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


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
        parsed_bucket=None,
        parsed_object_key=None,
        task_id=None,
        created_at=now,
        updated_at=now,
    )


def make_parsed_document(document_id, knowledge_base_id):
    document = make_document(document_id, knowledge_base_id, DEFAULT_USER_ID)
    document.status = PARSED_STATUS
    document.parsed_bucket = PARSED_RESULTS_BUCKET
    document.parsed_object_key = (
        f"users/{DEFAULT_USER_ID}/knowledge_bases/{knowledge_base_id}"
        f"/parsed/{document_id}.json"
    )
    return document


def make_chunk(chunk_id, document, chunk_index):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return Chunk(
        id=chunk_id,
        user_id=document.user_id,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        chunk_index=chunk_index,
        title=f"title {chunk_index}",
        content=f"content {chunk_index}",
        chapter="chapter",
        section=None,
        subsection=None,
        status="created",
        vector_id=None,
        created_at=now,
        updated_at=now,
    )


def run_async(coro):
    import asyncio

    return asyncio.run(coro)
