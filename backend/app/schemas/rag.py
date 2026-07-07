from pydantic import BaseModel, Field, field_validator


class RagAnswerRequest(BaseModel):
    """单知识库 RAG 问答请求。"""

    query: str
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        """避免空问题进入 embedding 和大模型调用。"""
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query


class RagSourceInfo(BaseModel):
    """引用来源的文档和章节信息。"""

    file_name: str
    chapter: str | None
    section: str | None
    subsection: str | None


class MultiKnowledgeBaseRagSourceInfo(RagSourceInfo):
    """多知识库 RAG 的引用来源，需要额外展示知识库名称。"""

    knowledge_base_name: str


class RagSource(BaseModel):
    """RAG 返回给前端展示的单条引用依据。"""

    chunk_id: str
    document_id: str
    score: float
    content: str
    source: RagSourceInfo


class MultiKnowledgeBaseRagSource(BaseModel):
    """多知识库 RAG 返回给前端展示的单条引用依据。"""

    chunk_id: str
    document_id: str
    knowledge_base_id: str
    score: float
    content: str
    source: MultiKnowledgeBaseRagSourceInfo


class RagAnswerResponse(BaseModel):
    """单知识库 RAG 问答响应。"""

    query: str
    knowledge_base_id: str
    top_k: int
    answer: str
    sources: list[RagSource]


class MultiKnowledgeBaseRagAnswerRequest(BaseModel):
    """多知识库 RAG 问答请求。"""

    query: str
    knowledge_base_ids: list[str]
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        """避免空问题进入 embedding 和大模型调用。"""
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query

    @field_validator("knowledge_base_ids")
    @classmethod
    def knowledge_base_ids_must_not_be_empty(cls, value: list[str]) -> list[str]:
        """知识库列表必填，并按输入顺序去重。"""
        deduplicated: list[str] = []
        for item in value:
            kb_id = item.strip()
            if kb_id and kb_id not in deduplicated:
                deduplicated.append(kb_id)
        if not deduplicated:
            raise ValueError("knowledge_base_ids must not be empty")
        return deduplicated


class MultiKnowledgeBaseRagAnswerResponse(BaseModel):
    """多知识库 RAG 问答响应。"""

    qa_record_id: str | None = None
    query: str
    knowledge_base_ids: list[str]
    top_k: int
    answer: str
    sources: list[MultiKnowledgeBaseRagSource]
