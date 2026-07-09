"""Seed a development-only demo RAG knowledge base.

This script is intentionally separate from the production upload-processing
flow. It reads the files under ../example, creates MySQL documents/chunks,
generates embeddings with Ollama, writes them to Milvus, and marks the chunks
as embedded so the existing RAG endpoints can be verified.

Run from the backend directory:

    python scripts/seed_demo_rag.py

Or in Docker:

    docker compose exec backend python scripts/seed_demo_rag.py
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.chunk import Chunk


DEMO_KB_ID = "kb_demo_seed"
DEMO_KB_NAME = "示例知识库"
DEMO_KB_DESCRIPTION = "由 example 语料生成的开发测试知识库"
DEMO_USER_ID = "default_user"
EXAMPLE_DIR = PROJECT_ROOT / "example"
EXAMPLE_FILE_NAMES = (
    "三国演义语料.md",
    "水浒传语料.md",
    "凡人修仙传语料.txt",
)
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
EMBEDDING_BATCH_SIZE = 16


@dataclass(frozen=True)
class DemoDocument:
    id: str
    file_name: str
    file_type: str
    file_size: int
    object_key: str
    content: str
    raw_bytes: bytes


@dataclass(frozen=True)
class SeedSummary:
    knowledge_base_id: str
    document_count: int
    chunk_count: int
    vector_count: int


def split_text_into_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text for the demo seed data, preferring paragraph boundaries."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap must be greater than or equal to 0 and less than chunk_size"
        )

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_text:
        return []

    chunks: list[str] = []
    current = ""
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", normalized_text)
        if paragraph.strip()
    ]

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(paragraph, chunk_size, chunk_overlap))
            continue

        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)

    return chunks


def _split_long_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    step = chunk_size - chunk_overlap
    while start < len(text):
        if start > 0 and len(text) - start <= chunk_overlap:
            break
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


async def seed_demo_rag() -> SeedSummary:
    from app.core.config import get_settings
    from app.core.database import get_database_pool, init_database
    from app.services.embedding_service import OllamaEmbeddingService

    settings = get_settings()
    await init_database()
    pool = await get_database_pool()

    storage = _create_document_storage(settings)
    vector_service = _create_vector_service(settings)
    embedding_service = OllamaEmbeddingService(
        model_name=settings.embedding_model_name,
        base_url=settings.ollama_base_url,
    )

    documents = _load_demo_documents(settings)
    async with pool.acquire() as connection:
        await _cleanup_existing_demo_data(
            connection=connection,
            storage=storage,
            vector_service=vector_service,
            settings=settings,
        )
        await _create_demo_knowledge_base(connection)
        await storage.ensure_bucket(settings.minio_bucket_documents)
        await _write_demo_documents(connection, storage, settings, documents)
        chunks = await _write_demo_chunks(connection, documents)

    vector_count = await _embed_and_store_chunks(
        pool=pool,
        chunks=chunks,
        embedding_service=embedding_service,
        vector_service=vector_service,
        embedding_dimension=settings.embedding_dimension,
    )

    async with pool.acquire() as connection:
        await _mark_documents_embedded(connection, [document.id for document in documents])

    return SeedSummary(
        knowledge_base_id=DEMO_KB_ID,
        document_count=len(documents),
        chunk_count=len(chunks),
        vector_count=vector_count,
    )


def _create_document_storage(settings: Any) -> Any:
    from minio import Minio

    from app.services.document_storage import MinIODocumentStorage

    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return MinIODocumentStorage(client)


def _create_vector_service(settings: Any) -> Any:
    from app.services.vector_service import MilvusVectorService

    return MilvusVectorService(
        host=settings.milvus_host,
        port=settings.milvus_port,
        collection_name=settings.milvus_collection_document_chunks,
        embedding_dimension=settings.embedding_dimension,
    )


def _load_demo_documents(settings: Any) -> list[DemoDocument]:
    documents: list[DemoDocument] = []
    missing_files: list[str] = []

    for file_name in EXAMPLE_FILE_NAMES:
        file_path = EXAMPLE_DIR / file_name
        if not file_path.exists():
            missing_files.append(str(file_path))
            continue

        raw_bytes = file_path.read_bytes()
        content = raw_bytes.decode("utf-8", errors="replace")
        file_hash = hashlib.sha1(file_name.encode("utf-8")).hexdigest()[:12]
        file_type = file_path.suffix.lower().lstrip(".") or "txt"
        object_key = (
            f"users/{DEMO_USER_ID}/knowledge_bases/{DEMO_KB_ID}/raw/{file_name}"
        )
        documents.append(
            DemoDocument(
                id=f"doc_demo_{file_hash}",
                file_name=file_name,
                file_type=file_type,
                file_size=len(raw_bytes),
                object_key=object_key,
                content=content,
                raw_bytes=raw_bytes,
            )
        )

    if missing_files:
        raise FileNotFoundError("Missing demo files: " + ", ".join(missing_files))
    if not documents:
        raise FileNotFoundError(f"No demo corpus files found under {EXAMPLE_DIR}")

    return documents


async def _cleanup_existing_demo_data(
    connection: Any,
    storage: Any,
    vector_service: Any,
    settings: Any,
) -> None:
    import aiomysql

    async with connection.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute(
            """
            SELECT id
            FROM knowledge_bases
            WHERE user_id = %s
              AND (id = %s OR name = %s)
            """,
            (DEMO_USER_ID, DEMO_KB_ID, DEMO_KB_NAME),
        )
        knowledge_base_rows = await cursor.fetchall()
        knowledge_base_ids = [str(row["id"]) for row in knowledge_base_rows]

        if knowledge_base_ids:
            placeholders = ", ".join(["%s"] * len(knowledge_base_ids))
            await cursor.execute(
                f"""
                SELECT storage_bucket, storage_object_key
                FROM documents
                WHERE user_id = %s
                  AND knowledge_base_id IN ({placeholders})
                """,
                (DEMO_USER_ID, *knowledge_base_ids),
            )
            object_rows = await cursor.fetchall()
        else:
            object_rows = []

    for knowledge_base_id in set([DEMO_KB_ID, *knowledge_base_ids]):
        vector_service.delete_chunk_embeddings_by_knowledge_base(
            DEMO_USER_ID,
            knowledge_base_id,
        )

    await storage.ensure_bucket(settings.minio_bucket_documents)
    for row in object_rows:
        await storage.delete_object(
            str(row["storage_bucket"]),
            str(row["storage_object_key"]),
        )

    async with connection.cursor() as cursor:
        if knowledge_base_ids:
            placeholders = ", ".join(["%s"] * len(knowledge_base_ids))
            await cursor.execute(
                f"""
                DELETE FROM chunks
                WHERE user_id = %s
                  AND knowledge_base_id IN ({placeholders})
                """,
                (DEMO_USER_ID, *knowledge_base_ids),
            )
            await cursor.execute(
                f"""
                DELETE FROM documents
                WHERE user_id = %s
                  AND knowledge_base_id IN ({placeholders})
                """,
                (DEMO_USER_ID, *knowledge_base_ids),
            )
            await cursor.execute(
                f"""
                DELETE FROM knowledge_bases
                WHERE user_id = %s
                  AND id IN ({placeholders})
                """,
                (DEMO_USER_ID, *knowledge_base_ids),
            )
    await connection.commit()


async def _create_demo_knowledge_base(connection: Any) -> None:
    now = _utc_now()
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO knowledge_bases (
                id,
                user_id,
                name,
                description,
                status,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, 'active', %s, %s)
            """,
            (
                DEMO_KB_ID,
                DEMO_USER_ID,
                DEMO_KB_NAME,
                DEMO_KB_DESCRIPTION,
                now,
                now,
            ),
        )
    await connection.commit()


async def _write_demo_documents(
    connection: Any,
    storage: Any,
    settings: Any,
    documents: list[DemoDocument],
) -> None:
    now = _utc_now()
    async with connection.cursor() as cursor:
        await cursor.executemany(
            """
            INSERT INTO documents (
                id,
                user_id,
                knowledge_base_id,
                file_name,
                file_type,
                file_size,
                storage_bucket,
                storage_object_key,
                status,
                error_message,
                parsed_bucket,
                parsed_object_key,
                task_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'chunked', NULL, NULL, NULL, NULL, %s, %s)
            """,
            [
                (
                    document.id,
                    DEMO_USER_ID,
                    DEMO_KB_ID,
                    document.file_name,
                    document.file_type,
                    document.file_size,
                    settings.minio_bucket_documents,
                    document.object_key,
                    now,
                    now,
                )
                for document in documents
            ],
        )
    await connection.commit()

    for document in documents:
        await storage.put_object(
            settings.minio_bucket_documents,
            document.object_key,
            document.raw_bytes,
            mimetypes.guess_type(document.file_name)[0] or "text/plain",
        )


async def _write_demo_chunks(
    connection: Any,
    documents: list[DemoDocument],
) -> list[Chunk]:
    now = _utc_now()
    chunks: list[Chunk] = []
    for document in documents:
        content_chunks = split_text_into_chunks(document.content)
        document_hash = hashlib.sha1(document.file_name.encode("utf-8")).hexdigest()[:10]
        chunks.extend(
            Chunk(
                id=f"chunk_demo_{document_hash}_{index:04d}",
                user_id=DEMO_USER_ID,
                knowledge_base_id=DEMO_KB_ID,
                document_id=document.id,
                chunk_index=index,
                title=None,
                content=content,
                chapter=None,
                section=None,
                subsection=None,
                status="created",
                vector_id=None,
                created_at=now,
                updated_at=now,
            )
            for index, content in enumerate(content_chunks)
        )

    async with connection.cursor() as cursor:
        await cursor.executemany(
            """
            INSERT INTO chunks (
                id,
                user_id,
                knowledge_base_id,
                document_id,
                chunk_index,
                title,
                content,
                chapter,
                section,
                subsection,
                status,
                vector_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)
            """,
            [
                (
                    chunk.id,
                    chunk.user_id,
                    chunk.knowledge_base_id,
                    chunk.document_id,
                    chunk.chunk_index,
                    chunk.title,
                    chunk.content,
                    chunk.chapter,
                    chunk.section,
                    chunk.subsection,
                    chunk.status,
                    chunk.created_at,
                    chunk.updated_at,
                )
                for chunk in chunks
            ],
        )
    await connection.commit()
    return chunks


async def _embed_and_store_chunks(
    pool: Any,
    chunks: list[Chunk],
    embedding_service: Any,
    vector_service: Any,
    embedding_dimension: int,
) -> int:
    vector_count = 0
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
        texts = [chunk.content for chunk in batch]
        embeddings = await asyncio.to_thread(embedding_service.embed_texts, texts)
        if len(embeddings) != len(batch):
            raise RuntimeError(
                f"Ollama returned {len(embeddings)} embeddings for {len(batch)} chunks"
            )
        _validate_embedding_dimension(embeddings, embedding_dimension)

        vector_ids = await asyncio.to_thread(
            vector_service.insert_chunk_embeddings,
            batch,
            embeddings,
        )
        if len(vector_ids) != len(batch):
            raise RuntimeError(
                f"Milvus returned {len(vector_ids)} vector ids for {len(batch)} chunks"
            )

        now = _utc_now()
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.executemany(
                    """
                    UPDATE chunks
                    SET vector_id = %s,
                        status = 'embedded',
                        updated_at = %s
                    WHERE id = %s
                      AND user_id = %s
                      AND knowledge_base_id = %s
                    """,
                    [
                        (
                            vector_id,
                            now,
                            chunk.id,
                            DEMO_USER_ID,
                            DEMO_KB_ID,
                        )
                        for chunk, vector_id in zip(batch, vector_ids, strict=True)
                    ],
                )
            await connection.commit()
        vector_count += len(vector_ids)
        print(
            f"Embedded batch {start // EMBEDDING_BATCH_SIZE + 1}: "
            f"{vector_count}/{len(chunks)} chunks"
        )

    return vector_count


async def _mark_documents_embedded(
    connection: Any,
    document_ids: list[str],
) -> None:
    if not document_ids:
        return

    placeholders = ", ".join(["%s"] * len(document_ids))
    async with connection.cursor() as cursor:
        await cursor.execute(
            f"""
            UPDATE documents
            SET status = 'embedded',
                error_message = NULL,
                updated_at = %s
            WHERE user_id = %s
              AND knowledge_base_id = %s
              AND id IN ({placeholders})
            """,
            (_utc_now(), DEMO_USER_ID, DEMO_KB_ID, *document_ids),
        )
    await connection.commit()


def _validate_embedding_dimension(
    embeddings: list[list[float]],
    expected_dimension: int,
) -> None:
    for index, embedding in enumerate(embeddings):
        if len(embedding) != expected_dimension:
            raise RuntimeError(
                "Embedding dimension mismatch: "
                f"chunk batch item {index} has dimension {len(embedding)}, "
                f"but settings.embedding_dimension is {expected_dimension}."
            )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _main() -> None:
    from app.core.database import close_database

    try:
        summary = await seed_demo_rag()
        print("")
        print("Demo RAG seed completed.")
        print(f"Knowledge base: {DEMO_KB_NAME} ({summary.knowledge_base_id})")
        print(f"Documents: {summary.document_count}")
        print(f"Chunks: {summary.chunk_count}")
        print(f"Milvus vectors: {summary.vector_count}")
        print("Select this knowledge base in the frontend to verify RAG retrieval.")
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(_main())
