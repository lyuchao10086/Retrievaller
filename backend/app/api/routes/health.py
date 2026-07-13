from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.health import check_dependencies_health


router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, object]:
    """Legacy aggregate health endpoint. It always returns diagnostics as 200."""
    return {
        "backend": {"status": "ok"},
        "dependencies": await check_dependencies_health(),
    }


@router.get("/health/live")
async def liveness_check() -> dict[str, object]:
    """Container/process probe that never waits on external dependencies."""
    return {"backend": {"status": "ok"}}


@router.get("/health/ready")
async def readiness_check() -> JSONResponse:
    """Return 503 until every required runtime dependency is ready."""
    dependencies = await check_dependencies_health()
    required_dependencies = (
        "mysql",
        "redis",
        "minio",
        "milvus",
        "ollama_embedding",
        "ollama_llm",
    )
    unready = [
        name
        for name in required_dependencies
        if dependencies.get(name, {}).get("status") != "ok"
    ]
    ready = not unready
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "backend": {"status": "ok" if ready else "error"},
            "dependencies": dependencies,
            "unready_dependencies": unready,
        },
    )
