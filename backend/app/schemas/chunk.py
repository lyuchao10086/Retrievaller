from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChunkResponse(BaseModel):
    """chunk 接口对外返回的数据结构。"""

    id: str
    user_id: str
    knowledge_base_id: str
    document_id: str
    chunk_index: int
    title: str | None
    content: str
    chapter: str | None
    section: str | None
    subsection: str | None
    status: str
    vector_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmbeddingStatusResponse(BaseModel):
    """文档 embedding 进度响应。"""

    document_id: str
    status: str
    total_chunks: int
    embedded_chunks: int
    pending_chunks: int
