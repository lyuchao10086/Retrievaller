import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from app.api.routes.document import (
    get_chunk_repository,
    get_document_repository,
    get_document_storage,
    get_embedding_service,
    get_knowledge_base_repository,
    get_processing_queue,
    get_vector_service,
)
from app.api.routes.knowledge_base import get_knowledge_base_config_repository
from app.main import app
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_base_config import KnowledgeBaseConfig, ProcessingConfig
from app.repositories.chunk import MySQLChunkRepository
from app.services.document import (
    DEFAULT_DOCUMENT_BUCKET,
    DELETED_STATUS,
    DELETING_STATUS,
    DocumentDeletionInProgressError,
    UPLOADED_STATUS,
    create_document_chunks,
    delete_document_with_cleanup,
    embed_document_chunks,
    get_document_by_id,
    get_document_embedding_status,
    list_documents_by_knowledge_base,
    parse_document_content,
    parse_document_to_storage,
    upload_document_to_knowledge_base,
)
from app.services.embedding_service import OllamaEmbeddingService
from app.services.knowledge_base import DEFAULT_USER_ID
from app.tasks import document_processing
from app.tasks.document_processing import _chunk_settings_kwargs, _normalize_task_args


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

    async def set_processing_config_by_id_and_knowledge_base(
        self,
        user_id,
        knowledge_base_id,
        document_id,
        processing_config_json,
        config_version,
        updated_at,
    ):
        document = await self.get_by_id_and_knowledge_base(
            user_id, knowledge_base_id, document_id
        )
        if document is None:
            return None
        document.processing_config_json = processing_config_json
        document.config_version = config_version
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

    async def rename_by_id_and_knowledge_base(
        self,
        user_id,
        knowledge_base_id,
        document_id,
        new_file_name,
        updated_at,
    ):
        document = await self.get_by_id_and_knowledge_base(
            user_id,
            knowledge_base_id,
            document_id,
        )
        if document is None:
            return None
        document.file_name = new_file_name
        document.updated_at = updated_at
        return document


class InMemoryChunkRepository:
    def __init__(self):
        self.items = []

    async def replace_by_document(self, user_id, knowledge_base_id, document_id, chunks):
        self.items = [
            item
            for item in self.items
            if not (
                item.user_id == user_id
                and item.knowledge_base_id == knowledge_base_id
                and item.document_id == document_id
            )
        ]
        self.items.extend(chunks)
        return chunks

    async def list_by_document(self, user_id, knowledge_base_id, document_id):
        return [
            item
            for item in self.items
            if item.user_id == user_id
            and item.knowledge_base_id == knowledge_base_id
            and item.document_id == document_id
        ]

    async def delete_by_document(self, user_id, knowledge_base_id, document_id):
        deleted = await self.list_by_document(user_id, knowledge_base_id, document_id)
        self.items = [
            item
            for item in self.items
            if not (
                item.user_id == user_id
                and item.knowledge_base_id == knowledge_base_id
                and item.document_id == document_id
            )
        ]
        return deleted

    async def update_embedding_results(self, user_id, knowledge_base_id, document_id, results, updated_at):
        result_by_chunk_id = dict(results)
        for item in self.items:
            if (
                item.user_id == user_id
                and item.knowledge_base_id == knowledge_base_id
                and item.document_id == document_id
                and item.id in result_by_chunk_id
            ):
                item.vector_id = result_by_chunk_id[item.id]
                item.status = "embedded"
                item.updated_at = updated_at
        return await self.list_by_document(user_id, knowledge_base_id, document_id)

    async def count_embedding_status(self, user_id, knowledge_base_id, document_id):
        chunks = await self.list_by_document(user_id, knowledge_base_id, document_id)
        embedded = [
            item for item in chunks if item.status == "embedded" and item.vector_id
        ]
        return {
            "total_chunks": len(chunks),
            "embedded_chunks": len(embedded),
            "pending_chunks": len(chunks) - len(embedded),
        }

    async def list_by_ids(self, user_id, knowledge_base_id, chunk_ids):
        return [
            item
            for item in self.items
            if item.user_id == user_id
            and item.knowledge_base_id == knowledge_base_id
            and item.id in chunk_ids
        ]

    async def list_by_ids_and_knowledge_base_ids(self, user_id, knowledge_base_ids, chunk_ids):
        return [
            item
            for item in self.items
            if item.user_id == user_id
            and item.knowledge_base_id in knowledge_base_ids
            and item.id in chunk_ids
        ]

    async def exists_embedded_by_knowledge_base(self, user_id, knowledge_base_id):
        return any(
            item.user_id == user_id
            and item.knowledge_base_id == knowledge_base_id
            and item.status == "embedded"
            and item.vector_id
            for item in self.items
        )

    async def exists_embedded_by_knowledge_base_ids(self, user_id, knowledge_base_ids):
        return any(
            item.user_id == user_id
            and item.knowledge_base_id in knowledge_base_ids
            and item.status == "embedded"
            and item.vector_id
            for item in self.items
        )


class FakeEmbeddingService:
    def __init__(self, dimension=3):
        self.dimension = dimension
        self.texts = []
        self.model_names = []

    def embed_texts(self, texts, model_name=None):
        self.texts.extend(texts)
        self.model_names.append(model_name)
        return [[float(index + 1)] * self.dimension for index, _ in enumerate(texts)]


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


class FakeProcessingQueue:
    def __init__(self):
        self.calls = []

    def delay(self, user_id, kb_id, document_id, chunk_settings=None):
        self.calls.append(
            {
                "user_id": user_id,
                "kb_id": kb_id,
                "document_id": document_id,
                "chunk_settings": chunk_settings,
            }
        )
        return type("FakeTask", (), {"id": f"task_{document_id}"})()


class FailingProcessingQueue:
    def delay(self, user_id, kb_id, document_id, chunk_settings=None):
        raise RuntimeError("Celery unavailable")


class InMemoryKnowledgeBaseConfigRepository:
    def __init__(self, config):
        self.config = config

    async def get_by_knowledge_base_and_user(self, knowledge_base_id, user_id):
        if (
            self.config.knowledge_base_id == knowledge_base_id
            and self.config.user_id == user_id
        ):
            return self.config
        return None

    async def insert(self, config):
        self.config = config
        return config

    async def update(self, config):
        self.config = config
        return config


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


class FailingInsertDocumentRepository(InMemoryDocumentRepository):
    async def insert(self, document):
        raise RuntimeError("MySQL unavailable")


class FailingDeleteDocumentStorage(InMemoryDocumentStorage):
    def __init__(self):
        super().__init__()
        self.fail_deletes = True

    async def delete_object(self, bucket_name, object_key):
        if self.fail_deletes:
            raise RuntimeError("MinIO unavailable")
        await super().delete_object(bucket_name, object_key)


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


def test_upload_document_removes_raw_object_when_document_insert_fails():
    knowledge_base = make_knowledge_base("kb_active")
    storage = InMemoryDocumentStorage()

    try:
        run_async(
            upload_document_to_knowledge_base(
                knowledge_base_repository=InMemoryKnowledgeBaseRepository([knowledge_base]),
                document_repository=FailingInsertDocumentRepository(),
                storage=storage,
                kb_id=knowledge_base.id,
                file_name="demo.txt",
                file_type="text/plain",
                content=b"hello",
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "MySQL unavailable"
    else:
        raise AssertionError("expected document insert failure")

    assert storage.objects == {}


def test_delete_document_cleanup_marks_deleted_after_vectors_objects_and_chunks_are_removed():
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    vector_service = FakeVectorService()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.status = "embedded"
    document.parsed_bucket = "rag-parsed-results"
    document.parsed_object_key = "parsed/doc_target.json"
    document_repository.items.append(document)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    chunk_repository.items.append(make_chunk("chunk_target", document, 0, "embedded", "vec_1", now))
    storage.objects[(document.storage_bucket, document.storage_object_key)] = {"data": b"raw", "content_type": "text/plain"}
    storage.objects[(document.parsed_bucket, document.parsed_object_key)] = {"data": b"{}", "content_type": "application/json"}

    deleted = run_async(
        delete_document_with_cleanup(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            vector_service=vector_service,
            kb_id=document.knowledge_base_id,
            document_id=document.id,
        )
    )

    assert deleted.status == DELETED_STATUS
    assert document.status == DELETED_STATUS
    assert chunk_repository.items == []
    assert storage.objects == {}
    assert vector_service.deleted_documents == [{
        "user_id": DEFAULT_USER_ID,
        "knowledge_base_id": document.knowledge_base_id,
        "document_id": document.id,
    }]


def test_delete_document_cleanup_keeps_deleting_status_after_storage_failure_and_can_retry():
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = FailingDeleteDocumentStorage()
    vector_service = FakeVectorService()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.status = "embedded"
    document_repository.items.append(document)
    storage.objects[(document.storage_bucket, document.storage_object_key)] = {"data": b"raw", "content_type": "text/plain"}

    try:
        run_async(
            delete_document_with_cleanup(
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                storage=storage,
                vector_service=vector_service,
                kb_id=document.knowledge_base_id,
                document_id=document.id,
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "MinIO unavailable"
    else:
        raise AssertionError("expected storage delete failure")

    assert document.status == DELETING_STATUS
    assert document.error_message == "MinIO unavailable"
    assert (document.storage_bucket, document.storage_object_key) in storage.objects

    storage.fail_deletes = False
    deleted = run_async(
        delete_document_with_cleanup(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            vector_service=vector_service,
            kb_id=document.knowledge_base_id,
            document_id=document.id,
        )
    )

    assert deleted.status == DELETED_STATUS
    assert storage.objects == {}


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


def test_parse_document_content_supports_txt_and_markdown_sections():
    txt_result = parse_document_content(
        "第一段内容。\n\n第二段内容。".encode("utf-8"),
        file_name="notes.txt",
        file_type="text/plain",
    )
    md_result = parse_document_content(
        "# 第一章\n开头内容\n\n## 第一节\n细节内容".encode("utf-8"),
        file_name="book.md",
        file_type="text/markdown",
    )

    assert txt_result["parser"] == "plain_text"
    assert [section["content"] for section in txt_result["sections"]] == [
        "第一段内容。",
        "第二段内容。",
    ]
    assert md_result["parser"] == "markdown"
    assert md_result["sections"] == [
        {"level": 1, "title": "第一章", "content": "开头内容"},
        {"level": 2, "title": "第一节", "content": "细节内容"},
    ]


def test_parse_document_does_not_restart_a_document_being_deleted():
    document_repository = InMemoryDocumentRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.status = DELETING_STATUS
    document_repository.items.append(document)

    try:
        run_async(
            parse_document_to_storage(
                document_repository=document_repository,
                storage=storage,
                kb_id=document.knowledge_base_id,
                document_id=document.id,
            )
        )
    except DocumentDeletionInProgressError:
        pass
    else:
        raise AssertionError("expected processing to stop for deleting document")

    assert document.status == DELETING_STATUS
    assert document.error_message is None


def test_create_document_chunks_splits_parsed_text_and_updates_document_status():
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.status = "parsed"
    document.parsed_bucket = "rag-parsed-results"
    document.parsed_object_key = "parsed/doc_target.json"
    document_repository.items.append(document)
    parsed_payload = {
        "document_id": document.id,
        "knowledge_base_id": document.knowledge_base_id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "parser": "plain_text",
        "sections": [
            {"title": "intro", "content": "一二三四五六七八九十"},
            {"title": "body", "content": "第二段"},
        ],
    }
    storage.objects[(document.parsed_bucket, document.parsed_object_key)] = {
        "data": json.dumps(parsed_payload, ensure_ascii=False).encode("utf-8"),
        "content_type": "application/json",
    }

    chunks = run_async(
        create_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            kb_id=document.knowledge_base_id,
            document_id=document.id,
            chunk_size=5,
            chunk_overlap=1,
        )
    )

    assert [chunk.content for chunk in chunks] == ["一二三四五", "五六七八九", "九十", "第二段"]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3]
    assert all(chunk.status == "chunked" and chunk.vector_id is None for chunk in chunks)
    assert document.status == "chunked"


def test_retry_failed_document_chunking_cleans_old_vectors_before_rebuilding_chunks():
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    vector_service = FakeVectorService()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.status = "failed"
    document.error_message = "previous embedding failure"
    document_repository.items.append(document)
    storage.objects[(document.storage_bucket, document.storage_object_key)] = {
        "data": "第一段内容。\n\n第二段内容。".encode("utf-8"),
        "content_type": "text/plain",
    }
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    chunk_repository.items.append(
        make_chunk("chunk_old", document, 0, "embedded", "vec_old", now)
    )

    chunks = run_async(
        create_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            vector_service=vector_service,
            kb_id=document.knowledge_base_id,
            document_id=document.id,
            chunk_size=500,
            chunk_overlap=50,
        )
    )

    assert [chunk.content for chunk in chunks] == ["第一段内容。", "第二段内容。"]
    assert all(chunk.status == "chunked" and chunk.vector_id is None for chunk in chunks)
    assert document.status == "chunked"
    assert chunk_repository.items == chunks
    assert vector_service.deleted_documents == [
        {
            "user_id": DEFAULT_USER_ID,
            "knowledge_base_id": document.knowledge_base_id,
            "document_id": document.id,
        }
    ]


def test_create_document_chunks_rejects_unsupported_raw_document_type():
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.file_name = "demo.pdf"
    document.file_type = "application/pdf"
    document_repository.items.append(document)
    storage.objects[(document.storage_bucket, document.storage_object_key)] = {
        "data": b"%PDF",
        "content_type": "application/pdf",
    }

    try:
        run_async(
            create_document_chunks(
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                storage=storage,
                kb_id=document.knowledge_base_id,
                document_id=document.id,
            )
        )
    except Exception as exc:
        error = exc
    else:
        error = None

    assert str(error) == "Only txt, md and markdown documents are supported"
    assert chunk_repository.items == []


def test_create_document_chunks_applies_separator_cleaning_and_size_settings():
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.status = "parsed"
    document.parsed_bucket = "rag-parsed-results"
    document.parsed_object_key = "parsed/doc_target.json"
    document_repository.items.append(document)
    parsed_payload = {
        "document_id": document.id,
        "knowledge_base_id": document.knowledge_base_id,
        "file_name": document.file_name,
        "file_type": document.file_type,
        "parser": "plain_text",
        "sections": [
            {
                "content": (
                    "第一段   内容 http://example.com\n\n"
                    "第二段\t内容 test@example.com"
                )
            }
        ],
    }
    storage.objects[(document.parsed_bucket, document.parsed_object_key)] = {
        "data": json.dumps(parsed_payload, ensure_ascii=False).encode("utf-8"),
        "content_type": "application/json",
    }

    chunks = run_async(
        create_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            kb_id=document.knowledge_base_id,
            document_id=document.id,
            chunk_size=6,
            chunk_overlap=2,
            separator="\n\n",
            replace_consecutive_whitespace=True,
            remove_urls_and_emails=True,
        )
    )

    assert [chunk.content for chunk in chunks] == [
        "第一段 内容",
        "第二段 内容",
    ]


def test_embed_document_chunks_writes_vectors_and_embedding_status():
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    embedding_service = FakeEmbeddingService(dimension=3)
    vector_service = FakeVectorService()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.status = "chunked"
    document_repository.items.append(document)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    chunk_repository.items.extend(
        [
            Chunk(
                id="chunk_1",
                user_id=DEFAULT_USER_ID,
                knowledge_base_id=document.knowledge_base_id,
                document_id=document.id,
                chunk_index=0,
                title=None,
                content="第一段",
                chapter=None,
                section=None,
                subsection=None,
                status="created",
                vector_id=None,
                created_at=now,
                updated_at=now,
            ),
            Chunk(
                id="chunk_2",
                user_id=DEFAULT_USER_ID,
                knowledge_base_id=document.knowledge_base_id,
                document_id=document.id,
                chunk_index=1,
                title=None,
                content="第二段",
                chapter=None,
                section=None,
                subsection=None,
                status="created",
                vector_id=None,
                created_at=now,
                updated_at=now,
            ),
        ]
    )

    status_payload = run_async(
        embed_document_chunks(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            embedding_service=embedding_service,
            vector_service=vector_service,
            kb_id=document.knowledge_base_id,
            document_id=document.id,
            expected_embedding_dimension=3,
        )
    )

    assert embedding_service.texts == ["第一段", "第二段"]
    assert vector_service.calls == [
        {
            "chunk_ids": ["chunk_1", "chunk_2"],
            "embeddings": [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]],
        }
    ]
    assert status_payload == {
        "document_id": document.id,
        "status": "embedded",
        "total_chunks": 2,
        "embedded_chunks": 2,
        "pending_chunks": 0,
    }
    assert [chunk.vector_id for chunk in chunk_repository.items] == [
        "vector_chunk_1",
        "vector_chunk_2",
    ]
    assert all(chunk.status == "embedded" for chunk in chunk_repository.items)
    assert document.status == "embedded"


def test_embed_document_chunks_reports_model_name_for_dimension_mismatch():
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    embedding_service = FakeEmbeddingService(dimension=3)
    vector_service = FakeVectorService()
    document = make_document("doc_dimension", "kb_target", DEFAULT_USER_ID)
    document.status = "chunked"
    document_repository.items.append(document)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    chunk_repository.items.append(
        make_chunk("chunk_dimension", document, 0, "chunked", None, now)
    )

    try:
        run_async(
            embed_document_chunks(
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                embedding_service=embedding_service,
                vector_service=vector_service,
                kb_id=document.knowledge_base_id,
                document_id=document.id,
                expected_embedding_dimension=4,
                embedding_model_name="embed-incompatible",
            )
        )
    except ValueError as exc:
        error_message = str(exc)
    else:
        raise AssertionError("Expected an embedding dimension mismatch")

    assert "embed-incompatible" in error_message
    assert "expected 4" in error_message
    assert "got 3" in error_message
    assert vector_service.calls == []
    assert document.status == "failed"


def test_document_lifecycle_keeps_processing_config_isolated_and_cleans_deleted_index():
    knowledge_base_one = make_knowledge_base("kb_one")
    knowledge_base_two = make_knowledge_base("kb_two")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository(
        [knowledge_base_one, knowledge_base_two]
    )
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    embedding_service = FakeEmbeddingService(dimension=3)
    vector_service = FakeVectorService()
    first_config = ProcessingConfig(
        separator="\\n\\n",
        chunk_size=100,
        chunk_overlap=0,
        replace_consecutive_whitespace=True,
        remove_urls_and_emails=True,
        embedding_model_name="embed-first",
    )
    second_config = ProcessingConfig(
        separator="\\n\\n",
        chunk_size=100,
        chunk_overlap=0,
        replace_consecutive_whitespace=False,
        remove_urls_and_emails=False,
        embedding_model_name="embed-second",
    )

    first_document = run_async(
        upload_document_to_knowledge_base(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            storage=storage,
            kb_id=knowledge_base_one.id,
            file_name="first.txt",
            file_type="text/plain",
            content=(
                b"alpha   https://example.test/path beta"
                + bytes([10, 10])
                + b"second line"
            ),
        )
    )
    second_document = run_async(
        upload_document_to_knowledge_base(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            storage=storage,
            kb_id=knowledge_base_two.id,
            file_name="second.txt",
            file_type="text/plain",
            content=(
                b"alpha   https://example.test/path beta"
                + bytes([10, 10])
                + b"second line"
            ),
        )
    )

    assert first_document is not None
    assert second_document is not None

    for document, config in (
        (first_document, first_config),
        (second_document, second_config),
    ):
        run_async(
            parse_document_to_storage(
                document_repository=document_repository,
                storage=storage,
                kb_id=document.knowledge_base_id,
                document_id=document.id,
            )
        )
        run_async(
            create_document_chunks(
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                storage=storage,
                vector_service=vector_service,
                kb_id=document.knowledge_base_id,
                document_id=document.id,
                separator=config.separator,
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
                replace_consecutive_whitespace=config.replace_consecutive_whitespace,
                remove_urls_and_emails=config.remove_urls_and_emails,
            )
        )
        run_async(
            embed_document_chunks(
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                embedding_service=embedding_service,
                vector_service=vector_service,
                kb_id=document.knowledge_base_id,
                document_id=document.id,
                expected_embedding_dimension=3,
                embedding_model_name=config.embedding_model_name,
            )
        )

    first_chunks = run_async(
        chunk_repository.list_by_document(
            DEFAULT_USER_ID, knowledge_base_one.id, first_document.id
        )
    )
    second_chunks = run_async(
        chunk_repository.list_by_document(
            DEFAULT_USER_ID, knowledge_base_two.id, second_document.id
        )
    )
    assert [chunk.content for chunk in first_chunks] == ["alpha beta", "second line"]
    assert [chunk.content for chunk in second_chunks] == [
        "alpha   https://example.test/path beta",
        "second line",
    ]
    assert embedding_service.model_names == ["embed-first", "embed-second"]
    assert first_document.status == "embedded"
    assert second_document.status == "embedded"

    deleted = run_async(
        delete_document_with_cleanup(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            storage=storage,
            vector_service=vector_service,
            kb_id=knowledge_base_one.id,
            document_id=first_document.id,
        )
    )

    assert deleted.status == DELETED_STATUS
    assert run_async(
        get_document_by_id(
            document_repository,
            knowledge_base_one.id,
            first_document.id,
        )
    ) is None
    assert run_async(
        chunk_repository.list_by_document(
            DEFAULT_USER_ID, knowledge_base_one.id, first_document.id
        )
    ) == []
    assert all(first_document.id not in key for _, key in storage.objects)
    assert vector_service.deleted_documents[-1] == {
        "user_id": DEFAULT_USER_ID,
        "knowledge_base_id": knowledge_base_one.id,
        "document_id": first_document.id,
    }
    assert run_async(
        chunk_repository.list_by_document(
            DEFAULT_USER_ID, knowledge_base_two.id, second_document.id
        )
    ) == second_chunks


def test_async_document_task_uses_the_persisted_processing_snapshot(monkeypatch):
    calls = []

    class FakePool:
        def acquire(self):
            return self

        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    async def fake_init_database():
        calls.append("database_initialized")

    async def fake_get_database_pool():
        return FakePool()

    async def fake_parse_document_to_storage(**kwargs):
        calls.append(("parse", kwargs["document_id"]))

    async def fake_create_document_chunks(**kwargs):
        calls.append(
            (
                "chunks",
                kwargs["chunk_size"],
                kwargs["chunk_overlap"],
                kwargs["replace_consecutive_whitespace"],
            )
        )

    async def fake_embed_document_chunks(**kwargs):
        calls.append(
            (
                "embed",
                kwargs["embedding_model_name"],
                kwargs["expected_embedding_dimension"],
            )
        )

    settings = SimpleNamespace(
        minio_endpoint="minio.test:9000",
        minio_access_key="access",
        minio_secret_key="secret",
        minio_secure=False,
        ollama_base_url="http://ollama.test",
        milvus_host="milvus.test",
        milvus_port=19530,
        milvus_collection_document_chunks="chunks",
        embedding_dimension=3,
        embedding_model_name="embed-default",
        minio_bucket_parsed_results="parsed-results",
    )
    monkeypatch.setattr(document_processing, "get_settings", lambda: settings)
    monkeypatch.setattr(document_processing, "init_database", fake_init_database)
    monkeypatch.setattr(document_processing, "get_database_pool", fake_get_database_pool)
    monkeypatch.setattr(document_processing, "MySQLDocumentRepository", lambda _: object())
    monkeypatch.setattr(document_processing, "MySQLChunkRepository", lambda _: object())
    monkeypatch.setattr(document_processing, "Minio", lambda **_: object())
    monkeypatch.setattr(document_processing, "MinIODocumentStorage", lambda _: object())
    monkeypatch.setattr(document_processing, "OllamaEmbeddingService", lambda **_: object())
    monkeypatch.setattr(document_processing, "MilvusVectorService", lambda **_: object())
    monkeypatch.setattr(
        document_processing, "parse_document_to_storage", fake_parse_document_to_storage
    )
    monkeypatch.setattr(
        document_processing, "create_document_chunks", fake_create_document_chunks
    )
    monkeypatch.setattr(
        document_processing, "embed_document_chunks", fake_embed_document_chunks
    )

    result = run_async(
        document_processing._process_document(
            DEFAULT_USER_ID,
            "kb_target",
            "doc_target",
            {
                "separator": "\\n\\n",
                "chunk_size": 300,
                "chunk_overlap": 30,
                "replace_consecutive_whitespace": True,
                "remove_urls_and_emails": False,
                "embedding_model_name": "embed-snapshot",
            },
        )
    )

    assert result == {
        "user_id": DEFAULT_USER_ID,
        "kb_id": "kb_target",
        "document_id": "doc_target",
        "status": "embedded",
    }
    assert calls == [
        "database_initialized",
        ("parse", "doc_target"),
        ("chunks", 300, 30, True),
        ("embed", "embed-snapshot", 3),
    ]


def test_get_document_embedding_status_counts_pending_chunks():
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    document = make_document("doc_target", "kb_target", DEFAULT_USER_ID)
    document.status = "chunked"
    document_repository.items.append(document)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    chunk_repository.items.extend(
        [
            make_chunk("chunk_1", document, 0, "embedded", "vec_1", now),
            make_chunk("chunk_2", document, 1, "created", None, now),
        ]
    )

    status_payload = run_async(
        get_document_embedding_status(
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            kb_id=document.knowledge_base_id,
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


def test_mysql_chunk_repository_from_row_can_be_called_on_instance():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    repository = MySQLChunkRepository(connection=None)

    chunk = repository._from_row(
        {
            "id": "chunk_1",
            "user_id": DEFAULT_USER_ID,
            "knowledge_base_id": "kb_target",
            "document_id": "doc_target",
            "chunk_index": 0,
            "title": None,
            "content": "hello",
            "chapter": None,
            "section": None,
            "subsection": None,
            "status": "created",
            "vector_id": None,
            "created_at": now,
            "updated_at": now,
        }
    )

    assert chunk.id == "chunk_1"
    assert chunk.content == "hello"
    assert chunk.status == "created"


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


def test_document_api_can_upload_and_list_documents():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    embedding_service = FakeEmbeddingService(dimension=1024)
    vector_service = FakeVectorService()
    processing_queue = FakeProcessingQueue()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_processing_queue] = lambda: processing_queue
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
    assert uploaded["status"] == "uploaded"
    assert uploaded["task_id"] is None
    assert uploaded["error_message"] is None
    assert chunk_repository.items == []
    assert vector_service.calls == []
    assert processing_queue.calls == []

    assert list_response.status_code == 200
    assert list_response.json() == [uploaded]


def test_document_api_upload_does_not_enqueue_unsupported_document():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    embedding_service = FakeEmbeddingService(dimension=1024)
    vector_service = FakeVectorService()
    processing_queue = FakeProcessingQueue()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_processing_queue] = lambda: processing_queue
    try:
        client = TestClient(app)
        upload_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/upload",
            files={"file": ("demo.pdf", b"%PDF", "application/pdf")},
        )
    finally:
        app.dependency_overrides.clear()

    assert upload_response.status_code == 201
    uploaded = upload_response.json()
    assert uploaded["file_name"] == "demo.pdf"
    assert uploaded["status"] == "uploaded"
    assert uploaded["task_id"] is None
    assert processing_queue.calls == []


def test_document_upload_api_accepts_chunk_settings_without_enqueueing():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    embedding_service = FakeEmbeddingService(dimension=1024)
    vector_service = FakeVectorService()
    processing_queue = FakeProcessingQueue()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_processing_queue] = lambda: processing_queue
    try:
        client = TestClient(app)
        upload_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/upload",
            data={
                "chunk_settings": json.dumps(
                    {
                        "separator": "\\n\\n",
                        "chunk_size": 8,
                        "chunk_overlap": 2,
                        "replace_consecutive_whitespace": True,
                        "remove_urls_and_emails": False,
                    }
                )
            },
            files={"file": ("demo.txt", b"hello", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert upload_response.status_code == 201
    uploaded = upload_response.json()
    assert uploaded["status"] == "uploaded"
    assert uploaded["task_id"] is None
    assert processing_queue.calls == []


def test_document_upload_rejects_invalid_chunk_settings_before_persisting_file():
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
        response = TestClient(app).post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/upload",
            data={"chunk_settings": "not-json"},
            files={"file": ("demo.txt", b"hello", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid chunk_settings"}
    assert document_repository.items == []
    assert storage.objects == {}


def test_document_process_api_enqueues_supported_document_for_retry():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document.status = "failed"
    document.error_message = "previous failure"
    document_repository.items.append(document)
    processing_queue = FakeProcessingQueue()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_processing_queue] = lambda: processing_queue
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/process"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "message": "Document processing queued",
        "document_id": document.id,
        "task_id": f"task_{document.id}",
        "status": "parsing",
    }
    assert document.status == "parsing"
    assert document.error_message is None
    assert document.task_id == f"task_{document.id}"
    assert processing_queue.calls == [
        {
            "user_id": DEFAULT_USER_ID,
            "kb_id": knowledge_base.id,
            "document_id": document.id,
                "chunk_settings": {
                    "separator": "\\n\\n",
                    "chunk_size": 500,
                    "chunk_overlap": 50,
                    "replace_consecutive_whitespace": False,
                    "remove_urls_and_emails": False,
                    "embedding_model_name": "quentinz/bge-large-zh-v1.5:latest",
                },
        }
    ]


def test_document_process_api_passes_chunk_settings_to_queue():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document_repository.items.append(document)
    processing_queue = FakeProcessingQueue()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_processing_queue] = lambda: processing_queue
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/process",
            json={
                "separator": "\\n\\n",
                "chunk_size": 6,
                "chunk_overlap": 2,
                    "replace_consecutive_whitespace": True,
                    "remove_urls_and_emails": True,
                },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert processing_queue.calls == [
        {
            "user_id": DEFAULT_USER_ID,
            "kb_id": knowledge_base.id,
            "document_id": document.id,
            "chunk_settings": {
                "separator": "\\n\\n",
                "chunk_size": 6,
                "chunk_overlap": 2,
                "replace_consecutive_whitespace": True,
                "remove_urls_and_emails": True,
                "embedding_model_name": "quentinz/bge-large-zh-v1.5:latest",
            },
        }
    ]


def test_document_process_api_rejects_duplicate_submission_while_processing():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document.status = "embedding"
    document.task_id = "task_existing"
    document_repository.items.append(document)
    processing_queue = FakeProcessingQueue()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_processing_queue] = lambda: processing_queue
    try:
        client = TestClient(app)
        response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/process"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "Document is already processing"
    assert document.task_id == "task_existing"
    assert document.status == "embedding"
    assert processing_queue.calls == []


def test_document_process_api_marks_document_failed_when_queue_submission_fails():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = lambda: knowledge_base_repository
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_processing_queue] = lambda: FailingProcessingQueue()
    try:
        response = TestClient(app).post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/process"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Document processing queue is unavailable"}
    assert document.status == "failed"
    assert document.error_message == "Celery unavailable"


def test_document_process_api_rejects_document_being_deleted():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document.status = DELETING_STATUS
    document_repository.items.append(document)
    processing_queue = FakeProcessingQueue()

    app.dependency_overrides[get_knowledge_base_repository] = lambda: knowledge_base_repository
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_processing_queue] = lambda: processing_queue
    try:
        response = TestClient(app).post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/process"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {"detail": "Document is deleting"}
    assert processing_queue.calls == []


def test_document_processing_status_api_returns_task_error_and_chunk_counts():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document.status = "failed"
    document.task_id = "task_failed"
    document.error_message = "Ollama unavailable"
    document_repository.items.append(document)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    chunk_repository.items.extend(
        [
            make_chunk("chunk_embedded", document, 0, "embedded", "vec_1", now),
            make_chunk("chunk_pending", document, 1, "chunked", None, now),
        ]
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/processing-status"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "document_id": document.id,
        "status": "failed",
        "task_id": "task_failed",
        "error_message": "Ollama unavailable",
        "total_chunks": 2,
        "embedded_chunks": 1,
        "pending_chunks": 1,
    }


def test_document_processing_task_filters_supported_chunk_settings_for_service():
    kwargs = _chunk_settings_kwargs(
        {
            "separator": "\\n\\n",
            "chunk_size": 300,
            "chunk_overlap": 30,
            "replace_consecutive_whitespace": True,
            "remove_urls_and_emails": True,
            "semantic": True,
            "parent_child_chunks": True,
        }
    )

    assert kwargs == {
        "separator": "\\n\\n",
        "chunk_size": 300,
        "chunk_overlap": 30,
        "replace_consecutive_whitespace": True,
        "remove_urls_and_emails": True,
    }


def test_document_processing_task_normalizes_new_and_legacy_argument_shapes():
    assert _normalize_task_args(
        "default_user",
        "kb_target",
        "doc_target",
        {"chunk_size": 300},
    ) == (
        "default_user",
        "kb_target",
        "doc_target",
        {"chunk_size": 300},
    )
    assert _normalize_task_args(
        "kb_legacy",
        "doc_legacy",
        {"chunk_size": 200},
        None,
    ) == (
        DEFAULT_USER_ID,
        "kb_legacy",
        "doc_legacy",
        {"chunk_size": 200},
    )


def test_document_api_can_hard_delete_document_by_id():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    vector_service = FakeVectorService()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document.parsed_bucket = "rag-parsed-results"
    document.parsed_object_key = "parsed/doc_target.json"
    document_repository.items.append(document)
    chunk_repository.items.append(
        make_chunk(
            "chunk_target",
            document,
            0,
            "embedded",
            "vec_target",
            datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
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
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
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
    assert deleted["status"] == DELETED_STATUS
    assert document in document_repository.items
    assert document.status == DELETED_STATUS
    assert chunk_repository.items == []
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
    chunk_repository = InMemoryChunkRepository()
    document_repository.items.append(
        make_document("doc_target", "kb_missing", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
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
    chunk_repository = InMemoryChunkRepository()
    document_repository.items.append(
        make_document("doc_target", "kb_other", DEFAULT_USER_ID)
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
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
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    embedding_service = FakeEmbeddingService(dimension=1024)
    vector_service = FakeVectorService()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
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
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    embedding_service = FakeEmbeddingService(dimension=1024)
    vector_service = FakeVectorService()

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
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


def test_document_processing_api_parse_chunk_status_and_embed_text_document():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    embedding_service = FakeEmbeddingService(dimension=1024)
    vector_service = FakeVectorService()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document.file_name = "doc_target.md"
    document.file_type = "text/markdown"
    storage.objects[(document.storage_bucket, document.storage_object_key)] = {
        "data": b"# Title\nhello world\n\nsecond paragraph",
        "content_type": document.file_type,
    }
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    try:
        client = TestClient(app)
        parse_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/parse"
        )
        parsed_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/parsed"
        )
        chunks_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/chunks"
        )
        status_before_embed_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/embedding-status"
        )
        embed_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/embed"
        )
        status_after_embed_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/embedding-status"
        )
    finally:
        app.dependency_overrides.clear()

    assert parse_response.status_code == 200
    assert parse_response.json() == {
        "message": "Document parsed synchronously",
        "document_id": document.id,
        "task_id": f"sync_{document.id}",
        "status": "parsed",
    }
    assert parsed_response.status_code == 200
    assert parsed_response.json()["sections"] == [
        {"level": 1, "title": "Title", "content": "hello world\nsecond paragraph"}
    ]
    assert chunks_response.status_code == 200
    chunk_payload = chunks_response.json()
    assert len(chunk_payload) == 1
    assert chunk_payload[0]["document_id"] == document.id
    assert chunk_payload[0]["content"] == "hello world\nsecond paragraph"
    assert chunk_payload[0]["status"] == "chunked"
    assert status_before_embed_response.status_code == 200
    assert status_before_embed_response.json() == {
        "document_id": document.id,
        "status": "chunked",
        "total_chunks": 1,
        "embedded_chunks": 0,
        "pending_chunks": 1,
    }
    assert embed_response.status_code == 200
    assert embed_response.json() == {
        "document_id": document.id,
        "status": "embedded",
        "total_chunks": 1,
        "embedded_chunks": 1,
        "pending_chunks": 0,
    }
    assert status_after_embed_response.status_code == 200
    assert status_after_embed_response.json() == embed_response.json()


def test_document_processing_api_can_chunk_uploaded_text_without_parse_step():
    knowledge_base = make_knowledge_base("kb_active")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    embedding_service = FakeEmbeddingService(dimension=1024)
    vector_service = FakeVectorService()
    document = make_document("doc_target", knowledge_base.id, DEFAULT_USER_ID)
    document.file_name = "doc_target.txt"
    document.file_type = "text/plain"
    storage.objects[(document.storage_bucket, document.storage_object_key)] = {
        "data": "第一段内容。\n\n第二段内容。".encode("utf-8"),
        "content_type": document.file_type,
    }
    document_repository.items.append(document)

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_embedding_service] = lambda: embedding_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    try:
        client = TestClient(app)
        chunks_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/chunks"
        )
        embed_response = client.post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/embed"
        )
        status_response = client.get(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/embedding-status"
        )
    finally:
        app.dependency_overrides.clear()

    assert chunks_response.status_code == 200
    assert [chunk["content"] for chunk in chunks_response.json()] == [
        "第一段内容。",
        "第二段内容。",
    ]
    assert all(chunk["status"] == "chunked" for chunk in chunks_response.json())
    assert vector_service.deleted_documents[0] == {
        "user_id": DEFAULT_USER_ID,
        "knowledge_base_id": knowledge_base.id,
        "document_id": document.id,
    }
    assert embed_response.status_code == 200
    assert embed_response.json() == {
        "document_id": document.id,
        "status": "embedded",
        "total_chunks": 2,
        "embedded_chunks": 2,
        "pending_chunks": 0,
    }
    assert status_response.status_code == 200
    assert status_response.json() == embed_response.json()
    assert document.status == "embedded"


def test_create_chunks_api_uses_knowledge_base_processing_config():
    knowledge_base = make_knowledge_base("kb_configured")
    knowledge_base_repository = InMemoryKnowledgeBaseRepository([knowledge_base])
    document_repository = InMemoryDocumentRepository()
    chunk_repository = InMemoryChunkRepository()
    storage = InMemoryDocumentStorage()
    vector_service = FakeVectorService()
    document = make_document("doc_configured", knowledge_base.id, DEFAULT_USER_ID)
    document.file_name = "configured.txt"
    document.file_type = "text/plain"
    storage.objects[(document.storage_bucket, document.storage_object_key)] = {
        "data": b"first   part https://example.test/path\n\nsecond\tpart",
        "content_type": document.file_type,
    }
    document_repository.items.append(document)
    config_repository = InMemoryKnowledgeBaseConfigRepository(
        KnowledgeBaseConfig(
            knowledge_base_id=knowledge_base.id,
            user_id=DEFAULT_USER_ID,
            processing=ProcessingConfig(
                separator="\\n\\n",
                chunk_size=100,
                chunk_overlap=0,
                replace_consecutive_whitespace=True,
                remove_urls_and_emails=True,
                embedding_model_name="embed-test",
            ),
        )
    )

    app.dependency_overrides[get_knowledge_base_repository] = (
        lambda: knowledge_base_repository
    )
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_chunk_repository] = lambda: chunk_repository
    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_knowledge_base_config_repository] = (
        lambda: config_repository
    )
    try:
        response = TestClient(app).post(
            f"/api/knowledge-bases/{knowledge_base.id}/documents/{document.id}/chunks"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [chunk["content"] for chunk in response.json()] == [
        "first part",
        "second part",
    ]


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


def make_chunk(chunk_id, document, chunk_index, status, vector_id, now):
    return Chunk(
        id=chunk_id,
        user_id=document.user_id,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        chunk_index=chunk_index,
        title=None,
        content=f"chunk {chunk_index}",
        chapter=None,
        section=None,
        subsection=None,
        status=status,
        vector_id=vector_id,
        created_at=now,
        updated_at=now,
    )


def run_async(coro):
    import asyncio

    return asyncio.run(coro)
