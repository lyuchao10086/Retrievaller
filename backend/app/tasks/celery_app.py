from celery import Celery

from app.core.config import build_redis_url, get_settings


settings = get_settings()

# Celery 使用 Redis 作为 broker 和 result backend。
# broker 负责接收待执行任务，result backend 先用于保存任务执行结果。
celery_app = Celery(
    "retrievaller",
    broker=build_redis_url(),
    backend=build_redis_url(settings.redis_result_db),
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
