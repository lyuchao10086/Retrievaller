from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]

# Pydantic 会自动把环境变量转换成正确类型
class Settings(BaseSettings):
    app_name: str = "retrievaller"
    app_env: str = "development"
    app_version: str = "development"

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "retrievaller"
    mysql_password: str = "retrievaller"
    mysql_database: str = "retrievaller"

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_result_db: int = 1
    celery_task_soft_time_limit_seconds: int = 900
    celery_task_time_limit_seconds: int = 960

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "retrievaller"
    minio_secret_key: str = "retrievaller"
    minio_secure: bool = False
    minio_bucket_documents: str = "rag-documents"
    minio_bucket_parsed_results: str = "rag-parsed-results"

    milvus_host: str = "milvus"
    milvus_port: int = 19530
    milvus_collection_document_chunks: str = "document_chunks"

    embedding_model_name: str = "quentinz/bge-large-zh-v1.5:latest"
    embedding_dimension: int = 1024
    ollama_base_url: str = "http://host.docker.internal:11434"
    local_llm_model: str = "qwen3:latest"
    rerank_base_url: str = ""
    rerank_model_name: str = ""

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"

    jwt_secret_key: str = "development-only-change-me"
    access_token_expire_minutes: int = 60 * 12

    health_check_timeout_seconds: float = 2.0
    log_level: str = "INFO"
    log_format: str = "json"

    # 前端开发服务和后端端口不同，需要显式允许跨域来源。
    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def build_redis_url(db: int | None = None) -> str:
    """构造 Redis URL，供 Celery broker/result backend 使用。"""
    settings = get_settings()
    redis_db = settings.redis_db if db is None else db
    return f"redis://{settings.redis_host}:{settings.redis_port}/{redis_db}"
