from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Chunk:
    """文档 chunk 内部实体。

    chunk 归属于 user_id + knowledge_base_id + document_id，避免跨知识库串数据。
    """

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
