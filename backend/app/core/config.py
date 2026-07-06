from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]

# Pydantic 会自动把环境变量转换成正确类型
class Settings(BaseSettings):
    app_name: str = "retrievaller"
    app_env: str = "development"

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "retrievaller"
    mysql_password: str = "retrievaller"
    mysql_database: str = "retrievaller"

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_result_db: int = 1

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "retrievaller"
    minio_secret_key: str = "retrievaller"
    minio_secure: bool = False
    minio_bucket_documents: str = "rag-documents"

    milvus_host: str = "milvus"
    milvus_port: int = 19530

    health_check_timeout_seconds: float = 2.0

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
