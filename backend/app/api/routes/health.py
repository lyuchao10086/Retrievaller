from fastapi import APIRouter

from app.services.health import check_dependencies_health


router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, object]:
    return {
        "backend": {"status": "ok"},
        "dependencies": await check_dependencies_health(),
    }
