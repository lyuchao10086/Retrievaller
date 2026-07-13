from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.repositories.knowledge_base import KnowledgeBaseRepository
from app.schemas.rag import (
    MultiKnowledgeBaseRagAnswerResponse,
    MultiKnowledgeBaseRagSource,
    MultiKnowledgeBaseRagSourceInfo,
    RagAnswerResponse,
    RagSource,
    RagSourceInfo,
)
from app.services.document import KnowledgeBaseNotFoundError
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_base import DEFAULT_USER_ID
from app.services.local_llm_service import LocalLLMService
from app.models.knowledge_base_config import KnowledgeBaseConfig
from app.services.rerank_service import HttpRerankService
from app.services.retrieval_service import (
    retrieve_chunks_for_query,
    retrieve_chunks_for_query_in_knowledge_bases,
)
from app.services.vector_service import VectorService


NO_RETRIEVAL_ANSWER = "当前知识库中没有检索到与问题相关的内容。"
NO_MULTI_RETRIEVAL_ANSWER = "当前选择的知识库中没有检索到与问题相关的内容。"
MAX_REFERENCE_CONTENT_CHARS = 1600

SYSTEM_PROMPT = """你是一个严谨的知识库问答助手。
你只能根据给定的参考资料回答问题。
如果参考资料中没有足够信息，必须回答“根据当前知识库资料无法确定”。
不要编造参考资料中没有出现的事实、人物、数字、结论或文档名。
不要把引用来源写成不存在的文档名，只能使用参考资料中给出的编号和来源。

输出格式：
1. 先直接回答问题，内容简洁、准确、有条理。
2. 然后列出“依据”，用要点说明答案分别依据了哪些参考资料编号。
3. 如果资料不足，只说明无法确定，并简要说明缺少哪类资料。"""

MULTI_KB_SYSTEM_PROMPT = """你是一个严谨的知识库问答助手。
你只能根据给定的参考资料回答问题。
如果参考资料中没有足够信息，必须回答“根据当前选择的知识库资料无法确定”。
不要编造参考资料中没有出现的事实、人物、数字、结论或文档名。
不要把引用来源写成不存在的知识库名或文档名，只能使用参考资料中给出的编号和来源。

输出格式：
1. 先直接回答问题，内容简洁、准确、有条理。
2. 然后列出“依据”，用要点说明答案分别依据了哪些参考资料编号。
3. 如果资料不足，只说明无法确定，并简要说明缺少哪类资料。"""


class InvalidKnowledgeBasesError(ValueError):
    """多知识库 RAG 请求中包含不存在或无权访问的知识库。"""

    def __init__(self, invalid_knowledge_base_ids: list[str]):
        super().__init__("Invalid knowledge_base_ids")
        self.invalid_knowledge_base_ids = invalid_knowledge_base_ids


class IncompatibleKnowledgeBaseGenerationConfigError(ValueError):
    """多知识库请求不能在不确定的生成参数下执行。"""


MULTI_KB_GENERATION_CONFIG_MISMATCH_MESSAGE = (
    "Selected knowledge bases use different generation settings. "
    "Select one knowledge base or align their LLM configuration."
)


async def answer_single_knowledge_base_question(
    knowledge_base_repository: KnowledgeBaseRepository,
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    embedding_service: EmbeddingService,
    vector_service: VectorService,
    llm_service: LocalLLMService,
    kb_id: str,
    query: str,
    top_k: int,
    user_id: str = DEFAULT_USER_ID,
    config: KnowledgeBaseConfig | None = None,
    rerank_service: HttpRerankService | None = None,
) -> RagAnswerResponse:
    """单知识库 RAG：检索当前知识库 chunks，再调用本地大模型总结答案。"""
    knowledge_base = await knowledge_base_repository.get_active_by_id_and_user(
        kb_id,
        user_id,
    )
    if knowledge_base is None:
        raise KnowledgeBaseNotFoundError("Knowledge base not found")

    has_embedded_chunks = await chunk_repository.exists_embedded_by_knowledge_base(
        user_id=user_id,
        knowledge_base_id=kb_id,
    )
    if not has_embedded_chunks:
        return RagAnswerResponse(
            query=query,
            knowledge_base_id=kb_id,
            top_k=top_k,
            answer=NO_RETRIEVAL_ANSWER,
            sources=[],
        )

    effective_top_k = config.retrieval.top_k if config is not None else top_k
    candidate_count = (
        config.retrieval.rerank_candidate_count
        if config is not None and config.retrieval.rerank_enabled
        else effective_top_k
    )
    retrieved_chunks = await retrieve_chunks_for_query(
        embedding_service=embedding_service,
        vector_service=vector_service,
        chunk_repository=chunk_repository,
        document_repository=document_repository,
        query=query,
        user_id=user_id,
        knowledge_base_id=kb_id,
        top_k=candidate_count,
        embedding_model_name=(
            config.processing.embedding_model_name if config is not None else None
        ),
    )
    retrieved_chunks = await _apply_retrieval_config(
        query, retrieved_chunks, config, rerank_service
    )

    sources = [
        RagSource(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            score=chunk.score,
            content=chunk.content,
            source=RagSourceInfo(
                file_name=chunk.source.file_name,
                chapter=chunk.source.chapter,
                section=chunk.source.section,
                subsection=chunk.source.subsection,
            ),
        )
        for chunk in retrieved_chunks
    ]
    if not sources:
        return RagAnswerResponse(
            query=query,
            knowledge_base_id=kb_id,
            top_k=top_k,
            answer=NO_RETRIEVAL_ANSWER,
            sources=[],
        )

    answer = await llm_service.generate_answer(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_build_user_prompt(query, sources),
    )
    return RagAnswerResponse(
        query=query,
        knowledge_base_id=kb_id,
        top_k=effective_top_k,
        answer=answer,
        sources=sources,
    )


async def answer_multi_knowledge_base_question(
    knowledge_base_repository: KnowledgeBaseRepository,
    document_repository: DocumentRepository,
    chunk_repository: ChunkRepository,
    embedding_service: EmbeddingService,
    vector_service: VectorService,
    llm_service: LocalLLMService,
    knowledge_base_ids: list[str],
    query: str,
    top_k: int,
    user_id: str = DEFAULT_USER_ID,
    configs: dict[str, KnowledgeBaseConfig] | None = None,
    rerank_service: HttpRerankService | None = None,
) -> MultiKnowledgeBaseRagAnswerResponse:
    """多知识库 RAG：只在用户选择的知识库范围内检索并生成答案。"""
    knowledge_bases = await knowledge_base_repository.list_active_by_ids_and_user(
        knowledge_base_ids,
        user_id,
    )
    found_ids = {knowledge_base.id for knowledge_base in knowledge_bases}
    invalid_ids = [kb_id for kb_id in knowledge_base_ids if kb_id not in found_ids]
    if invalid_ids:
        raise InvalidKnowledgeBasesError(invalid_ids)

    _ensure_compatible_generation_configs(knowledge_base_ids, configs)

    has_embedded_chunks = (
        await chunk_repository.exists_embedded_by_knowledge_base_ids(
            user_id=user_id,
            knowledge_base_ids=knowledge_base_ids,
        )
    )
    if not has_embedded_chunks:
        return MultiKnowledgeBaseRagAnswerResponse(
            query=query,
            knowledge_base_ids=knowledge_base_ids,
            top_k=top_k,
            answer=NO_MULTI_RETRIEVAL_ANSWER,
            sources=[],
        )

    if configs is None:
        retrieved_chunks = await retrieve_chunks_for_query_in_knowledge_bases(
            embedding_service=embedding_service,
            vector_service=vector_service,
            chunk_repository=chunk_repository,
            document_repository=document_repository,
            knowledge_base_repository=knowledge_base_repository,
            query=query,
            user_id=user_id,
            knowledge_base_ids=knowledge_base_ids,
            top_k=top_k,
        )
    else:
        retrieved_chunks = []
        for knowledge_base_id in knowledge_base_ids:
            config = configs[knowledge_base_id]
            candidate_count = (
                config.retrieval.rerank_candidate_count
                if config.retrieval.rerank_enabled
                else config.retrieval.top_k
            )
            per_knowledge_base = await retrieve_chunks_for_query(
                embedding_service=embedding_service,
                vector_service=vector_service,
                chunk_repository=chunk_repository,
                document_repository=document_repository,
                query=query,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                top_k=candidate_count,
                embedding_model_name=config.processing.embedding_model_name,
            )
            retrieved_chunks.extend(
                await _apply_retrieval_config(
                    query, per_knowledge_base, config, rerank_service
                )
            )

    sources = [
        MultiKnowledgeBaseRagSource(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            knowledge_base_id=chunk.knowledge_base_id,
            score=chunk.score,
            content=chunk.content,
            source=MultiKnowledgeBaseRagSourceInfo(
                knowledge_base_name=chunk.source.knowledge_base_name
                or chunk.knowledge_base_id,
                file_name=chunk.source.file_name,
                chapter=chunk.source.chapter,
                section=chunk.source.section,
                subsection=chunk.source.subsection,
            ),
        )
        for chunk in retrieved_chunks
    ]
    if not sources:
        return MultiKnowledgeBaseRagAnswerResponse(
            query=query,
            knowledge_base_ids=knowledge_base_ids,
            top_k=top_k,
            answer=NO_MULTI_RETRIEVAL_ANSWER,
            sources=[],
        )

    primary_config = configs[knowledge_base_ids[0]] if configs else None
    answer = await llm_service.generate_answer(
        system_prompt=MULTI_KB_SYSTEM_PROMPT,
        user_prompt=_build_multi_kb_user_prompt(query, sources),
        model_name=(primary_config.generation.llm_model_name if primary_config else None),
        temperature=(primary_config.generation.temperature if primary_config else None),
        max_tokens=(primary_config.generation.max_tokens if primary_config else None),
    )
    return MultiKnowledgeBaseRagAnswerResponse(
        query=query,
        knowledge_base_ids=knowledge_base_ids,
        top_k=top_k,
        answer=answer,
        sources=sources,
    )


def _ensure_compatible_generation_configs(
    knowledge_base_ids: list[str],
    configs: dict[str, KnowledgeBaseConfig] | None,
) -> None:
    """Reject ambiguous multi-KB generation requests before retrieval begins."""
    if configs is None or len(knowledge_base_ids) < 2:
        return

    reference_generation = configs[knowledge_base_ids[0]].generation_dict()
    if any(
        configs[knowledge_base_id].generation_dict() != reference_generation
        for knowledge_base_id in knowledge_base_ids[1:]
    ):
        raise IncompatibleKnowledgeBaseGenerationConfigError(
            MULTI_KB_GENERATION_CONFIG_MISMATCH_MESSAGE
        )


async def _apply_retrieval_config(
    query: str,
    chunks,
    config: KnowledgeBaseConfig | None,
    rerank_service: HttpRerankService | None,
):
    if config is None:
        return chunks
    filtered = [
        chunk for chunk in chunks if chunk.score >= config.retrieval.similarity_threshold
    ]
    if config.retrieval.rerank_enabled:
        if rerank_service is None:
            raise RuntimeError("Rerank is enabled but unavailable")
        ranking = await rerank_service.rerank(
            query,
            [chunk.content for chunk in filtered],
            config.retrieval.rerank_model_name,
        )
        reranked = []
        for result in ranking:
            chunk = filtered[result.index]
            chunk.score = result.score
            reranked.append(chunk)
        filtered = reranked
    return filtered[: config.retrieval.top_k]


def _build_user_prompt(query: str, sources: list[RagSource]) -> str:
    """把检索结果组织成模型可读的参考资料列表。"""
    references: list[str] = []
    for index, source in enumerate(sources, start=1):
        references.append(
            "\n".join(
                [
                    f"[{index}]",
                    f"文档：{_format_source(source.source)}",
                    f"Document ID：{source.document_id}",
                    f"Chunk ID：{source.chunk_id}",
                    f"相似度分数：{source.score:.4f}",
                    f"原文：{_truncate_reference_content(source.content)}",
                ]
            )
        )

    return f"""用户问题：
{query}

参考资料：
{chr(10).join(references)}

请基于以上参考资料回答用户问题。
要求：
1. 先直接回答问题，再列出“依据”。
2. 只能根据参考资料回答，不要编造。
3. 如果资料不足，请回答“根据当前知识库资料无法确定”。
4. 引用依据时只使用参考资料编号，例如“依据：[1]、[2]”。
5. 不要写出参考资料中不存在的文档名、章节名或知识库名。"""


def _build_multi_kb_user_prompt(
    query: str,
    sources: list[MultiKnowledgeBaseRagSource],
) -> str:
    """把多知识库检索结果组织成模型可读的参考资料列表。"""
    references: list[str] = []
    for index, source in enumerate(sources, start=1):
        references.append(
            "\n".join(
                [
                    f"[{index}]",
                    f"知识库：{source.source.knowledge_base_name}",
                    f"知识库 ID：{source.knowledge_base_id}",
                    f"文档：{_format_multi_source(source.source)}",
                    f"Document ID：{source.document_id}",
                    f"Chunk ID：{source.chunk_id}",
                    f"相似度分数：{source.score:.4f}",
                    f"原文：{_truncate_reference_content(source.content)}",
                ]
            )
        )

    return f"""用户问题：
{query}

参考资料：
{chr(10).join(references)}

请基于以上参考资料回答用户问题。
要求：
1. 先直接回答问题，再列出“依据”。
2. 只能根据参考资料回答，不要编造。
3. 如果资料不足，请回答“根据当前选择的知识库资料无法确定”。
4. 引用依据时只使用参考资料编号，例如“依据：[1]、[2]”。
5. 不要写出参考资料中不存在的知识库名、文档名或章节名。"""


def _format_source(source: RagSourceInfo) -> str:
    parts = [
        source.file_name,
        source.chapter,
        source.section,
        source.subsection,
    ]
    return " - ".join(part for part in parts if part)


def _format_multi_source(source: MultiKnowledgeBaseRagSourceInfo) -> str:
    parts = [
        source.file_name,
        source.chapter,
        source.section,
        source.subsection,
    ]
    return " - ".join(part for part in parts if part)


def _truncate_reference_content(content: str) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= MAX_REFERENCE_CONTENT_CHARS:
        return normalized
    return f"{normalized[:MAX_REFERENCE_CONTENT_CHARS]}...（内容已截断）"
