from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/config")
async def get_system_config(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """返回前端可展示的非密钥运行配置。"""
    return {
        "app": {
            "name": settings.app_name,
            "env": settings.app_env,
        },
        "llm": {
            "provider": "ollama",
            "base_url": settings.ollama_base_url,
            "local_llm_model": settings.local_llm_model,
        },
        "embedding": {
            "provider": "ollama",
            "model_name": settings.embedding_model_name,
            "dimension": settings.embedding_dimension,
            "embedding_model_name": settings.embedding_model_name,
            "embedding_dimension": settings.embedding_dimension,
        },
        "storage": {
            "documents_bucket": settings.minio_bucket_documents,
            "parsed_results_bucket": settings.minio_bucket_parsed_results,
            "milvus_collection": settings.milvus_collection_document_chunks,
        },
        "document_processing": {
            "mode": "celery",
            "supported_file_types": [".txt", ".md", ".markdown"],
            "default_chunk_size": 500,
            "default_chunk_overlap": 50,
        },
        "evaluation": {
            "provider": "deepseek",
            "base_url": settings.deepseek_base_url,
            "model": settings.deepseek_model,
            "configured": bool(settings.deepseek_api_key.strip()),
        },
        "rerank": {
            "configured": bool(
                settings.rerank_base_url.strip() and settings.rerank_model_name.strip()
            ),
            "model_name": settings.rerank_model_name,
            "reason": "Rerank is enabled per knowledge base configuration.",
        },
    }
