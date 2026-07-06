from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    """提交文档解析任务后的响应结构。"""

    message: str
    document_id: str
    task_id: str
    status: str
