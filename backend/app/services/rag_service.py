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
from app.services.retrieval_service import (
    retrieve_chunks_for_query,
    retrieve_chunks_for_query_in_knowledge_bases,
)
from app.services.vector_service import VectorService


NO_RETRIEVAL_ANSWER = "当前知识库中没有检索到与问题相关的内容。"
NO_MULTI_RETRIEVAL_ANSWER = "当前选择的知识库中没有检索到与问题相关的内容。"

SYSTEM_PROMPT = """你是一个严谨的知识库问答助手。
你只能根据给定的参考资料回答问题。
如果参考资料中没有足够信息，请回答“根据当前知识库资料无法确定”。
不要编造参考资料中没有出现的事实。
回答要简洁、准确、有条理。
回答后必须给出引用来源。
引用来源格式为：文档名 - 章节 - 小节。
如果章节或小节为空，可以省略对应部分。"""

MULTI_KB_SYSTEM_PROMPT = """你是一个严谨的知识库问答助手。
你只能根据给定的参考资料回答问题。
如果参考资料中没有足够信息，请回答“根据当前选择的知识库资料无法确定”。
不要编造参考资料中没有出现的事实。
回答要简洁、准确、有条理。
回答后必须给出引用来源。
引用来源格式为：知识库名 / 文档名 - 章节 - 小节。
如果章节或小节为空，可以省略对应部分。"""


class InvalidKnowledgeBasesError(ValueError):
    """多知识库 RAG 请求中包含不存在或无权访问的知识库。"""

    def __init__(self, invalid_knowledge_base_ids: list[str]):
        super().__init__("Invalid knowledge_base_ids")
        self.invalid_knowledge_base_ids = invalid_knowledge_base_ids


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

    retrieved_chunks = await retrieve_chunks_for_query(
        embedding_service=embedding_service,
        vector_service=vector_service,
        chunk_repository=chunk_repository,
        document_repository=document_repository,
        query=query,
        user_id=user_id,
        knowledge_base_id=kb_id,
        top_k=top_k,
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
        top_k=top_k,
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

    answer = await llm_service.generate_answer(
        system_prompt=MULTI_KB_SYSTEM_PROMPT,
        user_prompt=_build_multi_kb_user_prompt(query, sources),
    )
    return MultiKnowledgeBaseRagAnswerResponse(
        query=query,
        knowledge_base_ids=knowledge_base_ids,
        top_k=top_k,
        answer=answer,
        sources=sources,
    )


def _build_user_prompt(query: str, sources: list[RagSource]) -> str:
    """把检索结果组织成模型可读的参考资料列表。"""
    references: list[str] = []
    for index, source in enumerate(sources, start=1):
        references.append(
            "\n".join(
                [
                    f"[{index}]",
                    f"来源：{_format_source(source.source)}",
                    f"内容：{source.content}",
                ]
            )
        )

    return f"""用户问题：
{query}

参考资料：
{chr(10).join(references)}

请基于以上参考资料回答用户问题。
要求：
1. 只能根据参考资料回答。
2. 不要编造。
3. 如果资料不足，请明确说明无法确定。
4. 回答后列出引用来源。"""


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
                    f"来源：{_format_multi_source(source.source)}",
                    f"内容：{source.content}",
                ]
            )
        )

    return f"""用户问题：
{query}

参考资料：
{chr(10).join(references)}

请基于以上参考资料回答用户问题。
要求：
1. 只能根据参考资料回答。
2. 不要编造。
3. 如果资料不足，请回答“根据当前选择的知识库资料无法确定”。
4. 回答要简洁、有条理。
5. 回答后列出引用来源，引用格式：知识库名 / 文档名 - 章节 - 小节。"""


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
