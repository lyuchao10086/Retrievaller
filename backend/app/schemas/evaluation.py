from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvaluationResponse(BaseModel):
    """答案评估接口返回结构。"""

    id: str
    qa_record_id: str
    faithfulness_score: int
    relevance_score: int
    citation_score: int
    completeness_score: int
    hallucination: bool
    overall_score: int
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvaluationCreateResult(EvaluationResponse):
    """创建评估结果响应，当前字段与 EvaluationResponse 一致。"""


class EvaluationListResponse(BaseModel):
    """评估列表接口返回结构，对齐前端 EvaluationListResponse。"""

    items: list[EvaluationResponse]
