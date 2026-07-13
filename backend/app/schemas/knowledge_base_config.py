from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProcessingConfigPayload(BaseModel):
    separator: str | None = Field(default=None, max_length=32)
    chunk_size: int | None = Field(default=None, ge=1, le=5000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1000)
    replace_consecutive_whitespace: bool | None = None
    remove_urls_and_emails: bool | None = None
    embedding_model_name: str | None = Field(default=None, min_length=1, max_length=255)


class RetrievalConfigPayload(BaseModel):
    top_k: int | None = Field(default=None, ge=1, le=20)
    similarity_threshold: float | None = Field(default=None, ge=-1, le=1)
    rerank_enabled: bool | None = None
    rerank_model_name: str | None = Field(default=None, max_length=255)
    rerank_candidate_count: int | None = Field(default=None, ge=1, le=100)


class GenerationConfigPayload(BaseModel):
    llm_model_name: str | None = Field(default=None, min_length=1, max_length=255)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)


class KnowledgeBaseConfigUpdate(BaseModel):
    processing: ProcessingConfigPayload | None = None
    retrieval: RetrievalConfigPayload | None = None
    generation: GenerationConfigPayload | None = None

    @model_validator(mode="after")
    def validate_non_empty_update(self) -> "KnowledgeBaseConfigUpdate":
        if self.processing is None and self.retrieval is None and self.generation is None:
            raise ValueError("At least one configuration section is required")
        return self


class ProcessingConfigResponse(BaseModel):
    separator: str | None
    chunk_size: int
    chunk_overlap: int
    replace_consecutive_whitespace: bool
    remove_urls_and_emails: bool
    embedding_model_name: str


class RetrievalConfigResponse(BaseModel):
    top_k: int
    similarity_threshold: float
    rerank_enabled: bool
    rerank_model_name: str
    rerank_candidate_count: int


class GenerationConfigResponse(BaseModel):
    llm_model_name: str
    temperature: float
    max_tokens: int


class KnowledgeBaseConfigResponse(BaseModel):
    knowledge_base_id: str
    processing: ProcessingConfigResponse
    retrieval: RetrievalConfigResponse
    generation: GenerationConfigResponse
    version: int
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
