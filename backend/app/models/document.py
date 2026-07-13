from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Document:
    """文档内部实体，用于在 service 层和 repository 层之间传递数据。"""

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
    processing_config_json: str | None = None
    config_version: int | None = None
    needs_reindex: bool = False
