import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.database import get_database_pool, init_database
from app.core.logging import bind_log_context, reset_log_context
from app.models.knowledge_base_config import GenerationConfig, KnowledgeBaseConfig, ProcessingConfig, RetrievalConfig
from app.repositories.benchmark import MySQLBenchmarkRepository
from app.repositories.chunk import MySQLChunkRepository
from app.repositories.document import MySQLDocumentRepository
from app.repositories.knowledge_base import MySQLKnowledgeBaseRepository
from app.services.benchmark import benchmark_cases_from_snapshot, execute_benchmark_run_cases
from app.services.deepseek_service import HttpxDeepSeekService
from app.services.embedding_service import OllamaEmbeddingService
from app.services.evaluation import evaluate_answer_content
from app.services.local_llm_service import OllamaLocalLLMService
from app.services.rag_service import answer_multi_knowledge_base_question
from app.services.rerank_service import HttpRerankService
from app.services.vector_service import MilvusVectorService
from app.tasks.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.benchmark_evaluation.run_benchmark")
def run_benchmark_task(self, user_id: str, knowledge_base_id: str, run_id: str) -> dict[str, str]:
    """Run a persisted benchmark without using FastAPI request dependencies."""
    token = bind_log_context(
        task_id=str(self.request.id or ""), user_id=user_id, knowledge_base_id=knowledge_base_id
    )
    try:
        return asyncio.run(_run_benchmark(user_id, knowledge_base_id, run_id, str(self.request.id or "")))
    except Exception:
        logger.exception("benchmark_run_failed", extra={"error_code": "benchmark_run_failed"})
        asyncio.run(_mark_run_failed(user_id, knowledge_base_id, run_id))
        raise
    finally:
        reset_log_context(token)


async def _run_benchmark(
    user_id: str, knowledge_base_id: str, run_id: str, task_id: str
) -> dict[str, str]:
    settings = get_settings()
    await init_database()
    pool = await get_database_pool()
    async with pool.acquire() as connection:
        repository = MySQLBenchmarkRepository(connection)
        run = await repository.get_run(run_id, knowledge_base_id, user_id)
        if run is None:
            raise LookupError("Benchmark run not found")
        if not run.task_id:
            run.task_id = task_id
            await repository.update_run(run)
        cases = benchmark_cases_from_snapshot(run)
        config = _config_from_snapshot(run.config_snapshot, knowledge_base_id, user_id)
        knowledge_base_repository = MySQLKnowledgeBaseRepository(connection)
        document_repository = MySQLDocumentRepository(connection)
        chunk_repository = MySQLChunkRepository(connection)
        embedding_service = OllamaEmbeddingService(
            model_name=config.processing.embedding_model_name,
            base_url=settings.ollama_base_url,
        )
        vector_service = MilvusVectorService(
            host=settings.milvus_host,
            port=settings.milvus_port,
            collection_name=settings.milvus_collection_document_chunks,
            embedding_dimension=settings.embedding_dimension,
        )
        llm_service = OllamaLocalLLMService(
            model_name=config.generation.llm_model_name,
            base_url=settings.ollama_base_url,
        )
        rerank_service = HttpRerankService(settings.rerank_base_url)
        deepseek_service = HttpxDeepSeekService(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=str(run.config_snapshot.get("models", {}).get("evaluator") or settings.deepseek_model),
        )

        async def answer_case(question: str, _snapshot: dict[str, object]):
            response = await answer_multi_knowledge_base_question(
                knowledge_base_repository=knowledge_base_repository,
                document_repository=document_repository,
                chunk_repository=chunk_repository,
                embedding_service=embedding_service,
                vector_service=vector_service,
                llm_service=llm_service,
                knowledge_base_ids=[knowledge_base_id],
                query=question,
                top_k=config.retrieval.top_k,
                user_id=user_id,
                configs={knowledge_base_id: config},
                rerank_service=rerank_service,
            )
            return response.answer, [source.model_dump(mode="json") for source in response.sources]

        async def evaluate_answer(question: str, answer: str, sources):
            return await evaluate_answer_content(
                deepseek_service,
                question=question,
                answer=answer,
                sources_json=sources,
                user_id=user_id,
            )

        completed = await execute_benchmark_run_cases(
            repository, run, cases, answer_case, evaluate_answer
        )
    return {"run_id": run_id, "status": completed.status}


async def _mark_run_failed(user_id: str, knowledge_base_id: str, run_id: str) -> None:
    """Persist a safe task-level failure when setup fails before per-case isolation begins."""
    try:
        await init_database()
        pool = await get_database_pool()
        async with pool.acquire() as connection:
            repository = MySQLBenchmarkRepository(connection)
            run = await repository.get_run(run_id, knowledge_base_id, user_id)
            if run is None:
                return
            run.status = "failed"
            run.error_message = "Benchmark task failed; inspect logs with the task ID"
            run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            run.updated_at = run.completed_at
            await repository.update_run(run)
    except Exception:
        logger.exception(
            "benchmark_failure_status_update_failed",
            extra={"error_code": "benchmark_failure_status_update_failed"},
        )


def _config_from_snapshot(
    snapshot: dict[str, object], knowledge_base_id: str, user_id: str
) -> KnowledgeBaseConfig:
    processing = snapshot.get("processing")
    retrieval = snapshot.get("retrieval")
    generation = snapshot.get("generation")
    return KnowledgeBaseConfig(
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        processing=ProcessingConfig(**processing) if isinstance(processing, dict) else ProcessingConfig(),
        retrieval=RetrievalConfig(**retrieval) if isinstance(retrieval, dict) else RetrievalConfig(),
        generation=GenerationConfig(**generation) if isinstance(generation, dict) else GenerationConfig(),
        version=int(snapshot.get("config_version") or 1),
    )
