from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass(slots=True)
class ProcessingConfig:
    separator: str | None = "\\n\\n"
    chunk_size: int = 500
    chunk_overlap: int = 50
    replace_consecutive_whitespace: bool = False
    remove_urls_and_emails: bool = False
    embedding_model_name: str = ""


@dataclass(slots=True)
class RetrievalConfig:
    top_k: int = 5
    similarity_threshold: float = 0.0
    rerank_enabled: bool = False
    rerank_model_name: str = ""
    rerank_candidate_count: int = 10


@dataclass(slots=True)
class GenerationConfig:
    llm_model_name: str = ""
    temperature: float = 0.2
    max_tokens: int = 1024


@dataclass(slots=True)
class KnowledgeBaseConfig:
    knowledge_base_id: str
    user_id: str
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def processing_dict(self) -> dict[str, object]:
        return asdict(self.processing)

    def retrieval_dict(self) -> dict[str, object]:
        return asdict(self.retrieval)

    def generation_dict(self) -> dict[str, object]:
        return asdict(self.generation)
