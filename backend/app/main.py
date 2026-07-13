from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.document import router as document_router
from app.api.routes.benchmark import router as benchmark_router
from app.api.routes.auth import router as auth_router
from app.api.routes.evaluation import router as evaluation_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge_base import router as knowledge_base_router
from app.api.routes.rag import multi_router as multi_rag_router
from app.api.routes.system import router as system_router
from app.core.config import get_settings
from app.core.database import close_database, init_database
from app.core.logging import bind_log_context, configure_logging, reset_log_context


logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


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
    configure_logging(settings.log_level, settings.log_format)
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(knowledge_base_router)
    application.include_router(document_router)
    application.include_router(benchmark_router)
    application.include_router(multi_rag_router)
    application.include_router(evaluation_router)
    application.include_router(system_router)

    @application.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", "")
        if not _REQUEST_ID_PATTERN.fullmatch(request_id):
            request_id = uuid4().hex
        context_token = bind_log_context(request_id=request_id)
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "error_code": "unhandled_request_error",
                },
            )
            raise
        else:
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                },
            )
            return response
        finally:
            reset_log_context(context_token)
    return application


app = create_app()
