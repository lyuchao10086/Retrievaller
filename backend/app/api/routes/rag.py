from typing import Annotated

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.repositories.chunk import ChunkRepository, MySQLChunkRepository
from app.repositories.document import DocumentRepository, MySQLDocumentRepository
from app.repositories.knowledge_base import (
    KnowledgeBaseRepository,
    MySQLKnowledgeBaseRepository,
)
from app.repositories.qa_record import MySQLQaRecordRepository, QaRecordRepository
from app.schemas.qa_record import QaRecordResponse
from app.schemas.rag import (
    MultiKnowledgeBaseRagAnswerRequest,
    MultiKnowledgeBaseRagAnswerResponse,
    RagAnswerRequest,
    RagAnswerResponse,
)
from app.services.document import KnowledgeBaseNotFoundError
from app.services.embedding_service import EmbeddingService, OllamaEmbeddingService
from app.services.local_llm_service import (
    LOCAL_LLM_UNAVAILABLE_MESSAGE,
    LocalLLMService,
    LocalLLMUnavailableError,
    OllamaLocalLLMService,
)
from app.services.rag_service import (
    InvalidKnowledgeBasesError,
    answer_multi_knowledge_base_question,
    answer_single_knowledge_base_question,
)
from app.services.qa_record import create_qa_record, list_qa_records
from app.services.vector_service import MilvusVectorService, VectorService


router = APIRouter(
    prefix="/api/knowledge-bases/{kb_id}/rag",
    tags=["rag"],
)
multi_router = APIRouter(
    prefix="/api/rag",
    tags=["rag"],
)


async def get_knowledge_base_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> KnowledgeBaseRepository:
    """RAG 接口先校验知识库是否属于当前默认用户。"""
    return MySQLKnowledgeBaseRepository(connection)


async def get_document_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> DocumentRepository:
    """RAG 来源展示需要回查文档名。"""
    return MySQLDocumentRepository(connection)


async def get_chunk_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> ChunkRepository:
    """RAG 来源展示需要回查 chunk 原文和章节信息。"""
    return MySQLChunkRepository(connection)


async def get_qa_record_repository(
    connection: Annotated[aiomysql.Connection, Depends(get_db_connection)],
) -> QaRecordRepository:
    """问答记录保存和查询使用同一个请求级 MySQL 连接。"""
    return MySQLQaRecordRepository(connection)


def get_embedding_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmbeddingService:
    """query embedding 必须复用 chunk embedding 使用的同一模型。"""
    return OllamaEmbeddingService(
        model_name=settings.embedding_model_name,
        base_url=settings.ollama_base_url,
    )


def get_vector_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VectorService:
    """创建 Milvus 检索服务。"""
    return MilvusVectorService(
        host=settings.milvus_host,
        port=settings.milvus_port,
        collection_name=settings.milvus_collection_document_chunks,
        embedding_dimension=settings.embedding_dimension,
    )


def get_local_llm_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LocalLLMService:
    """创建本地大模型服务；模型名和地址来自配置。"""
    return OllamaLocalLLMService(
        model_name=settings.local_llm_model,
        base_url=settings.ollama_base_url,
    )


@router.post("/answer", response_model=RagAnswerResponse)
async def answer_single_knowledge_base_api(
    kb_id: str,
    payload: RagAnswerRequest,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    chunk_repository: Annotated[
        ChunkRepository,
        Depends(get_chunk_repository),
    ],
    embedding_service: Annotated[
        EmbeddingService,
        Depends(get_embedding_service),
    ],
    vector_service: Annotated[
        VectorService,
        Depends(get_vector_service),
    ],
    llm_service: Annotated[
        LocalLLMService,
        Depends(get_local_llm_service),
    ],
) -> RagAnswerResponse:
    """单知识库 RAG 问答：检索当前 kb_id 下的 chunks，再调用本地 qwen3 总结。"""
    try:
        return await answer_single_knowledge_base_question(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            embedding_service=embedding_service,
            vector_service=vector_service,
            llm_service=llm_service,
            kb_id=kb_id,
            query=payload.query,
            top_k=payload.top_k,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        ) from exc
    except LocalLLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=LOCAL_LLM_UNAVAILABLE_MESSAGE,
        ) from exc


@multi_router.post("/answer", response_model=MultiKnowledgeBaseRagAnswerResponse)
async def answer_multi_knowledge_base_api(
    payload: MultiKnowledgeBaseRagAnswerRequest,
    knowledge_base_repository: Annotated[
        KnowledgeBaseRepository,
        Depends(get_knowledge_base_repository),
    ],
    document_repository: Annotated[
        DocumentRepository,
        Depends(get_document_repository),
    ],
    chunk_repository: Annotated[
        ChunkRepository,
        Depends(get_chunk_repository),
    ],
    embedding_service: Annotated[
        EmbeddingService,
        Depends(get_embedding_service),
    ],
    vector_service: Annotated[
        VectorService,
        Depends(get_vector_service),
    ],
    llm_service: Annotated[
        LocalLLMService,
        Depends(get_local_llm_service),
    ],
    qa_record_repository: Annotated[
        QaRecordRepository,
        Depends(get_qa_record_repository),
    ],
) -> MultiKnowledgeBaseRagAnswerResponse:
    """多知识库 RAG 问答：只在请求指定的 knowledge_base_ids 范围内检索。"""
    try:
        response = await answer_multi_knowledge_base_question(
            knowledge_base_repository=knowledge_base_repository,
            document_repository=document_repository,
            chunk_repository=chunk_repository,
            embedding_service=embedding_service,
            vector_service=vector_service,
            llm_service=llm_service,
            knowledge_base_ids=payload.knowledge_base_ids,
            query=payload.query,
            top_k=payload.top_k,
        )
        record = await create_qa_record(
            repository=qa_record_repository,
            question=response.query,
            answer=response.answer,
            knowledge_base_ids=response.knowledge_base_ids,
            sources_json=[
                source.model_dump(mode="json")
                for source in response.sources
            ],
        )
        return response.model_copy(update={"qa_record_id": record.id})
    except InvalidKnowledgeBasesError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Invalid knowledge_base_ids",
                "invalid_knowledge_base_ids": exc.invalid_knowledge_base_ids,
            },
        ) from exc
    except LocalLLMUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=LOCAL_LLM_UNAVAILABLE_MESSAGE,
        ) from exc


@multi_router.get("/records", response_model=list[QaRecordResponse])
async def list_rag_qa_records_api(
    qa_record_repository: Annotated[
        QaRecordRepository,
        Depends(get_qa_record_repository),
    ],
) -> list[QaRecordResponse]:
    """查询 default_user 最近 50 条 RAG 问答记录。"""
    records = await list_qa_records(qa_record_repository)
    return [QaRecordResponse.model_validate(record) for record in records]
