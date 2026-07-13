from celery import Celery

from app.core.config import build_redis_url, get_settings
from app.core.logging import configure_logging


settings = get_settings()
configure_logging(settings.log_level, settings.log_format)

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
    task_track_started=True,
    task_send_sent_event=True,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    task_time_limit=settings.celery_task_time_limit_seconds,
    worker_hijack_root_logger=False,
    imports=("app.tasks.document_processing", "app.tasks.benchmark_evaluation"),
)
