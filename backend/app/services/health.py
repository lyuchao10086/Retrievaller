import asyncio
from collections.abc import Awaitable, Callable
from uuid import uuid4

import aiomysql
from minio import Minio
from pymilvus import connections, utility
from redis.asyncio import Redis

from app.core.config import Settings, get_settings


HealthStatus = dict[str, str]
HealthCheck = Callable[[Settings], Awaitable[HealthStatus]]


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


async def _run_check(
    name: str,
    check: HealthCheck,
    settings: Settings,
) -> tuple[str, HealthStatus]:
    try:
        result = await asyncio.wait_for(
            check(settings),
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
    }
    results = await asyncio.gather(
        *(_run_check(name, check, settings) for name, check in checks.items())
    )
    return dict(results)
