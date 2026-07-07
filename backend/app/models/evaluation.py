from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Evaluation:
    """RAG 答案评估内部实体。"""

    id: str
    user_id: str
    qa_record_id: str
    faithfulness_score: int
    relevance_score: int
    citation_score: int
    completeness_score: int
    hallucination: bool
    overall_score: int
    reason: str
    raw_response: str
    created_at: datetime
    updated_at: datetime
