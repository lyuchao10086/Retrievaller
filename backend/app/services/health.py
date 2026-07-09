import asyncio
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from uuid import uuid4

import aiomysql
import httpx
from minio import Minio
from pymilvus import connections, utility
from redis.asyncio import Redis

from app.core.config import Settings, get_settings


HealthStatus = dict[str, str]
HealthCheck = Callable[[Settings], Awaitable[HealthStatus] | HealthStatus]


async def check_mysql(settings: Settings) -> HealthStatus:
    connection = await aiomysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        db=settings.mysql_database,
        connect_timeout=settings.health_check_timeout_seconds,
    )
    try:
        await connection.ping()
    finally:
        connection.close()
    return {"status": "ok"}


async def check_redis(settings: Settings) -> HealthStatus:
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        socket_connect_timeout=settings.health_check_timeout_seconds,
        socket_timeout=settings.health_check_timeout_seconds,
    )
    try:
        await client.ping()
    finally:
        await client.aclose()
    return {"status": "ok"}


async def check_minio(settings: Settings) -> HealthStatus:
    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    await asyncio.to_thread(client.list_buckets)
    return {"status": "ok"}


async def check_milvus(settings: Settings) -> HealthStatus:
    alias = f"health_{uuid4().hex}"
    try:
        await asyncio.to_thread(
            connections.connect,
            alias=alias,
            host=settings.milvus_host,
            port=settings.milvus_port,
            timeout=settings.health_check_timeout_seconds,
        )
        await asyncio.to_thread(utility.get_server_version, using=alias)
    finally:
        connections.disconnect(alias)
    return {"status": "ok"}


async def check_ollama_embedding(settings: Settings) -> HealthStatus:
    """检查 Ollama 是否在线，以及 embedding 模型是否已拉取。"""
    return await _check_ollama_model(settings, settings.embedding_model_name)


async def check_ollama_llm(settings: Settings) -> HealthStatus:
    """检查 Ollama 是否在线，以及本地 chat/LLM 模型是否已拉取。"""
    return await _check_ollama_model(settings, settings.local_llm_model)


def check_deepseek_config(settings: Settings) -> HealthStatus:
    """只检查 DeepSeek 配置是否存在，不发起外部 API 调用。"""
    if settings.deepseek_api_key.strip():
        return {
            "status": "ok",
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "detail": "DeepSeek API key is configured",
        }
    return {
        "status": "warning",
        "provider": "deepseek",
        "model": settings.deepseek_model,
        "detail": "DeepSeek API key is not configured",
    }


async def check_celery_config(settings: Settings) -> HealthStatus:
    """检查 Celery broker/result backend 配置和 Redis 连通性，不依赖 worker 存活。"""
    broker_url = _redis_url(settings, settings.redis_db)
    backend_url = _redis_url(settings, settings.redis_result_db)
    await _ping_redis_db(settings, settings.redis_db)
    await _ping_redis_db(settings, settings.redis_result_db)
    return {
        "status": "ok",
        "broker": broker_url,
        "backend": backend_url,
        "detail": "Celery broker and result backend Redis databases are reachable",
    }


async def _run_check(
    name: str,
    check: HealthCheck,
    settings: Settings,
) -> tuple[str, HealthStatus]:
    try:
        result = await asyncio.wait_for(
            _call_check(check, settings),
            timeout=settings.health_check_timeout_seconds,
        )
    except Exception as exc:
        return name, {"status": "error", "detail": str(exc)}
    return name, result


async def check_dependencies_health() -> dict[str, HealthStatus]:
    settings = get_settings()
    checks: dict[str, HealthCheck] = {
        "mysql": check_mysql,
        "redis": check_redis,
        "minio": check_minio,
        "milvus": check_milvus,
        "ollama_embedding": check_ollama_embedding,
        "ollama_llm": check_ollama_llm,
        "deepseek_config": check_deepseek_config,
        "celery_config": check_celery_config,
    }
    results = await asyncio.gather(
        *(_run_check(name, check, settings) for name, check in checks.items())
    )
    return dict(results)


async def _call_check(check: HealthCheck, settings: Settings) -> HealthStatus:
    result = check(settings)
    if isawaitable(result):
        return await result
    return result


async def _check_ollama_model(settings: Settings, model_name: str) -> HealthStatus:
    model_names = await _fetch_ollama_model_names(settings)
    if model_name in model_names:
        return {
            "status": "ok",
            "model": model_name,
            "detail": "Ollama is reachable and model is available",
        }
    return {
        "status": "warning",
        "model": model_name,
        "detail": "Ollama is reachable but configured model was not found",
    }


async def _fetch_ollama_model_names(settings: Settings) -> list[str]:
    base_url = settings.ollama_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=settings.health_check_timeout_seconds) as client:
        response = await client.get(f"{base_url}/api/tags")
        response.raise_for_status()
        payload = response.json()

    models = payload.get("models", [])
    if not isinstance(models, list):
        return []

    model_names: list[str] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        name = model.get("name") or model.get("model")
        if isinstance(name, str) and name:
            model_names.append(name)
    return model_names


async def _ping_redis_db(settings: Settings, db: int) -> None:
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=db,
        socket_connect_timeout=settings.health_check_timeout_seconds,
        socket_timeout=settings.health_check_timeout_seconds,
    )
    try:
        await client.ping()
    finally:
        await client.aclose()


def _redis_url(settings: Settings, db: int) -> str:
    return f"redis://{settings.redis_host}:{settings.redis_port}/{db}"
