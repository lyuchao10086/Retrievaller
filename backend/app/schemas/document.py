from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentResponse(BaseModel):
    """文档接口对外返回的数据结构。"""

    id: str
    user_id: str
    knowledge_base_id: str
    file_name: str
    file_type: str
    file_size: int
    storage_bucket: str
    storage_object_key: str
    status: str
    error_message: str | None
    parsed_bucket: str | None
    parsed_object_key: str | None
    task_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ParseTaskResponse(BaseModel):
    """同步解析接口返回，保留 task_id 字段方便后续迁移 Celery。"""

    message: str
    document_id: str
    task_id: str
    status: str


class ChunkSettingsRequest(BaseModel):
    """文档处理时可选的基础分段与清洗配置。"""

    separator: str | None = Field(default=None, max_length=32)
    chunk_size: int = Field(default=500, ge=1, le=5000)
    chunk_overlap: int = Field(default=50, ge=0, le=1000)
    replace_consecutive_whitespace: bool = False
    remove_urls_and_emails: bool = False

    @model_validator(mode="after")
    def chunk_overlap_must_be_smaller_than_size(self) -> "ChunkSettingsRequest":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self


class ParsedDocumentResponse(BaseModel):
    """解析结果 JSON 的基础结构。"""

    document_id: str | None = None
    knowledge_base_id: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    parser: str | None = None
    sections: list[dict[str, object]] = Field(default_factory=list)


class ChunkResponse(BaseModel):
    """文档 chunk 接口对外返回的数据结构。"""

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
    """文档 embedding 进度返回结构。"""

    document_id: str
    status: str
    total_chunks: int
    embedded_chunks: int
    pending_chunks: int


class ProcessingStatusResponse(EmbeddingStatusResponse):
    """文档后台处理进度，补充 Celery 任务和错误信息。"""

    task_id: str | None
    error_message: str | None
