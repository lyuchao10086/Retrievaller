from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from app.api.routes.document import router as document_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge_base import router as knowledge_base_router
from app.core.config import get_settings
from app.core.database import close_database, init_database


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """应用启动时打开共享资源，关闭时释放共享资源。"""
    await init_database()
    try:
        yield
    finally:
        await close_database()


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    settings = get_settings()
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.include_router(health_router)
    application.include_router(knowledge_base_router)
    application.include_router(document_router)
    return application


app = create_app()
