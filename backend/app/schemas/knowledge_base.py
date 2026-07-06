from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    """创建知识库接口的请求体。"""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class KnowledgeBaseResponse(BaseModel):
    """知识库接口对外返回的数据结构。"""

    id: str
    user_id: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
