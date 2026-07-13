from typing import Annotated
import logging

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.auth import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.core.database import get_db_connection
from app.core.logging import bind_log_context
from app.repositories.chunk import ChunkRepository, MySQLChunkRepository
from app.repositories.document import DocumentRepository, MySQLDocumentRepository
from app.repositories.knowledge_base import (
    KnowledgeBaseRepository,
    MySQLKnowledgeBaseRepository,
)
from app.repositories.knowledge_base_config import KnowledgeBaseConfigRepository
from app.api.routes.knowledge_base import get_knowledge_base_config_repository
from app.repositories.qa_record import MySQLQaRecordRepository, QaRecordRepository
from app.schemas.qa_record import QaRecordResponse
from app.schemas.rag import (
    MultiKnowledgeBaseRagAnswerRequest,
    MultiKnowledgeBaseRagAnswerResponse,
    RagSuggestionsRequest,
    RagSuggestionsResponse,
)
from app.services.embedding_service import EmbeddingService, OllamaEmbeddingService
from app.services.local_llm_service import (
    LOCAL_LLM_UNAVAILABLE_MESSAGE,
    LocalLLMService,
    LocalLLMUnavailableError,
    OllamaLocalLLMService,
)
from app.services.rag_service import (
    IncompatibleKnowledgeBaseGenerationConfigError,
    InvalidKnowledgeBasesError,
    answer_multi_knowledge_base_question,
)
from app.services.knowledge_base_config import get_or_create_knowledge_base_config
from app.services.rerank_service import (
    HttpRerankService,
    RerankUnavailableError,
)
from app.services.qa_record import (
    create_qa_record,
    delete_qa_record,
    generate_qa_record_title,
    list_qa_records,
)
from app.services.vector_service import MilvusVectorService, VectorService


multi_router = APIRouter(
    prefix="/api/rag",
    tags=["rag"],
    dependencies=[Depends(get_current_user)],
)
logger = logging.getLogger(__name__)


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


def get_rerank_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HttpRerankService:
    return HttpRerankService(settings.rerank_base_url)


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
    config_repository: Annotated[
        KnowledgeBaseConfigRepository,
        Depends(get_knowledge_base_config_repository),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    rerank_service: Annotated[HttpRerankService, Depends(get_rerank_service)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> MultiKnowledgeBaseRagAnswerResponse:
    """多知识库 RAG 问答：只在请求指定的 knowledge_base_ids 范围内检索。"""
    bind_log_context(knowledge_base_id=",".join(payload.knowledge_base_ids))
    try:
        knowledge_bases = await knowledge_base_repository.list_active_by_ids_and_user(
            payload.knowledge_base_ids, current_user.id
        )
        found_ids = {knowledge_base.id for knowledge_base in knowledge_bases}
        invalid_ids = [
            kb_id for kb_id in payload.knowledge_base_ids if kb_id not in found_ids
        ]
        if invalid_ids:
            raise InvalidKnowledgeBasesError(invalid_ids)
        configs = {
            kb_id: await get_or_create_knowledge_base_config(
                config_repository, kb_id, current_user.id, settings
            )
            for kb_id in payload.knowledge_base_ids
        }
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
            user_id=current_user.id,
            configs=configs,
            rerank_service=rerank_service,
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
            title=await generate_qa_record_title(
                llm_service,
                question=response.query,
                answer=response.answer,
            ),
            user_id=current_user.id,
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
    except IncompatibleKnowledgeBaseGenerationConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except LocalLLMUnavailableError as exc:
        logger.warning(
            "rag_local_llm_unavailable",
            extra={"error_code": "local_llm_unavailable"},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=LOCAL_LLM_UNAVAILABLE_MESSAGE,
        ) from exc
    except RerankUnavailableError as exc:
        logger.warning("rag_rerank_unavailable", extra={"error_code": "rerank_unavailable"})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rerank service unavailable",
        ) from exc


@multi_router.get("/records", response_model=list[QaRecordResponse])
async def list_rag_qa_records_api(
    qa_record_repository: Annotated[
        QaRecordRepository,
        Depends(get_qa_record_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[QaRecordResponse]:
    """查询当前用户最近 50 条 RAG 问答记录。"""
    records = await list_qa_records(qa_record_repository, current_user.id)
    return [QaRecordResponse.model_validate(record) for record in records]


@multi_router.delete("/records/{qa_record_id}", response_model=QaRecordResponse)
async def delete_rag_qa_record_api(
    qa_record_id: str,
    qa_record_repository: Annotated[
        QaRecordRepository,
        Depends(get_qa_record_repository),
    ],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> QaRecordResponse:
    """硬删除当前用户的一条 RAG 问答记录。"""
    record = await delete_qa_record(qa_record_repository, qa_record_id, current_user.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Qa record not found",
        )
    return QaRecordResponse.model_validate(record)


@multi_router.post("/suggestions", response_model=RagSuggestionsResponse)
async def create_rag_suggestions_api(
    payload: RagSuggestionsRequest,
    llm_service: Annotated[
        LocalLLMService,
        Depends(get_local_llm_service),
    ],
    _: Annotated[CurrentUser, Depends(get_current_user)],
) -> RagSuggestionsResponse:
    """为已登录用户根据知识库名称生成首页可点击的候选问题。"""
    kb_text = "、".join(payload.knowledge_base_names) or "默认知识库"
    fallback = _fallback_suggestions(kb_text, payload.count)
    try:
        raw_response = await llm_service.generate_answer(
            "你是知识库问答系统的提问建议生成器。只输出候选问题列表，不要解释。",
            (
                f"当前知识库：{kb_text}\n"
                f"请生成 {payload.count} 个用户可能会问的问题。"
                "每行一个问题，不要编号，不要 Markdown。问题要适合基于知识库检索回答。"
            ),
        )
    except LocalLLMUnavailableError:
        return RagSuggestionsResponse(suggestions=fallback)

    suggestions = _parse_suggestions(raw_response, payload.count)
    return RagSuggestionsResponse(suggestions=suggestions or fallback)


def _parse_suggestions(raw_response: str, count: int) -> list[str]:
    suggestions: list[str] = []
    for line in raw_response.splitlines():
        item = line.strip().lstrip("-*0123456789.、)） ").strip()
        if not item:
            continue
        if item not in suggestions:
            suggestions.append(item[:36])
        if len(suggestions) >= count:
            break
    return suggestions


def _fallback_suggestions(kb_text: str, count: int) -> list[str]:
    base = [
        f"总结{kb_text}中的核心结论",
        "这个文档主要讲了什么？",
        "列出回答中的引用来源",
        "检索到的原文依据有哪些？",
        "根据当前知识库资料能确定什么？",
        "请用条理化方式回答这个问题",
        "如果资料不足，请说明无法确定",
        "当前知识库里有哪些关键流程？",
    ]
    return base[:count]
