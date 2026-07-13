from dataclasses import dataclass

from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.repositories.knowledge_base import KnowledgeBaseRepository
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService


@dataclass(slots=True)
class RetrievedSourceInfo:
    """检索结果对应的可展示来源信息。"""

    file_name: str
    chapter: str | None
    section: str | None
    subsection: str | None
    knowledge_base_name: str | None = None


@dataclass(slots=True)
class RetrievedChunk:
    """Milvus 命中后回查 MySQL 得到的完整 chunk 引用。"""

    chunk_id: str
    document_id: str
    knowledge_base_id: str
    score: float
    content: str
    source: RetrievedSourceInfo


async def retrieve_chunks_for_query(
    embedding_service: EmbeddingService,
    vector_service: VectorService,
    chunk_repository: ChunkRepository,
    document_repository: DocumentRepository,
    query: str,
    user_id: str,
    knowledge_base_id: str,
    top_k: int,
) -> list[RetrievedChunk]:
    """在单个知识库沙箱中检索 query 相关 chunks，并回查来源元数据。"""
    query_embedding = embedding_service.embed_texts([query])[0]
    vector_hits = vector_service.search_chunk_embeddings(
        query_embedding=query_embedding,
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        top_k=top_k,
    )
    if not vector_hits:
        return []

    chunk_ids = [hit.chunk_id for hit in vector_hits]
    chunks = await chunk_repository.list_by_ids(
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        chunk_ids=chunk_ids,
    )
    chunk_by_id = {chunk.id: chunk for chunk in chunks}

    document_ids = sorted({chunk.document_id for chunk in chunks})
    documents = await document_repository.list_by_ids_and_knowledge_base(
        user_id=user_id,
        knowledge_base_id=knowledge_base_id,
        document_ids=document_ids,
    )
    document_by_id = {document.id: document for document in documents}

    # 按 Milvus score 顺序返回；如果 MySQL 中找不到对应 chunk，说明是脏向量，跳过。
    retrieved: list[RetrievedChunk] = []
    for hit in vector_hits:
        chunk = chunk_by_id.get(hit.chunk_id)
        if chunk is None:
            continue
        document = document_by_id.get(chunk.document_id)
        if document is None:
            continue
        retrieved.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                knowledge_base_id=chunk.knowledge_base_id,
                score=hit.score,
                content=chunk.content,
                source=RetrievedSourceInfo(
                    file_name=document.file_name,
                    chapter=chunk.chapter,
                    section=chunk.section,
                    subsection=chunk.subsection,
                ),
            )
        )
    return retrieved


async def retrieve_chunks_for_query_in_knowledge_bases(
    embedding_service: EmbeddingService,
    vector_service: VectorService,
    chunk_repository: ChunkRepository,
    document_repository: DocumentRepository,
    knowledge_base_repository: KnowledgeBaseRepository,
    query: str,
    user_id: str,
    knowledge_base_ids: list[str],
    top_k: int,
) -> list[RetrievedChunk]:
    """在多个指定知识库沙箱中检索 query 相关 chunks，并回查来源元数据。"""
    query_embedding = embedding_service.embed_texts([query])[0]
    vector_hits = vector_service.search_chunk_embeddings_in_knowledge_bases(
        query_embedding=query_embedding,
        user_id=user_id,
        knowledge_base_ids=knowledge_base_ids,
        top_k=top_k,
    )
    if not vector_hits:
        return []

    chunk_ids = [hit.chunk_id for hit in vector_hits]
    chunks = await chunk_repository.list_by_ids_and_knowledge_base_ids(
        user_id=user_id,
        knowledge_base_ids=knowledge_base_ids,
        chunk_ids=chunk_ids,
    )
    chunk_by_id = {chunk.id: chunk for chunk in chunks}

    document_ids = sorted({chunk.document_id for chunk in chunks})
    documents = await document_repository.list_by_ids_and_knowledge_base_ids(
        user_id=user_id,
        knowledge_base_ids=knowledge_base_ids,
        document_ids=document_ids,
    )
    document_by_id = {document.id: document for document in documents}

    knowledge_bases = await knowledge_base_repository.list_active_by_ids_and_user(
        knowledge_base_ids,
        user_id,
    )
    knowledge_base_by_id = {knowledge_base.id: knowledge_base for knowledge_base in knowledge_bases}

    # 按 Milvus score 顺序返回；MySQL 中找不到的脏向量跳过。
    retrieved: list[RetrievedChunk] = []
    for hit in vector_hits:
        chunk = chunk_by_id.get(hit.chunk_id)
        if chunk is None:
            continue
        document = document_by_id.get(chunk.document_id)
        knowledge_base = knowledge_base_by_id.get(chunk.knowledge_base_id)
        if document is None or knowledge_base is None:
            continue
        retrieved.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                knowledge_base_id=chunk.knowledge_base_id,
                score=hit.score,
                content=chunk.content,
                source=RetrievedSourceInfo(
                    file_name=document.file_name,
                    chapter=chunk.chapter,
                    section=chunk.section,
                    subsection=chunk.subsection,
                    knowledge_base_name=(
                        knowledge_base.name
                        if knowledge_base
                        else chunk.knowledge_base_id
                    ),
                ),
            )
        )
    return retrieved
