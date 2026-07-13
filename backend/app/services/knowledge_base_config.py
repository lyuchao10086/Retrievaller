from datetime import datetime, timezone

import httpx

from app.core.config import Settings
from app.models.knowledge_base_config import (
    GenerationConfig,
    KnowledgeBaseConfig,
    ProcessingConfig,
    RetrievalConfig,
)
from app.repositories.knowledge_base_config import KnowledgeBaseConfigRepository
from app.schemas.knowledge_base_config import KnowledgeBaseConfigUpdate
from app.services.rerank_service import HttpRerankService, RerankUnavailableError


class ModelConfigurationError(ValueError):
    """A user-selected model does not exist in the configured model service."""


class ConfigurationDependencyError(RuntimeError):
    """The service needed to validate an explicitly changed model is unavailable."""


def build_default_knowledge_base_config(
    knowledge_base_id: str,
    user_id: str,
    settings: Settings,
) -> KnowledgeBaseConfig:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return KnowledgeBaseConfig(
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        processing=ProcessingConfig(embedding_model_name=settings.embedding_model_name),
        retrieval=RetrievalConfig(
            rerank_model_name=settings.rerank_model_name,
        ),
        generation=GenerationConfig(llm_model_name=settings.local_llm_model),
        created_at=now,
        updated_at=now,
    )


def indexing_config_changed(
    current: KnowledgeBaseConfig,
    updated: KnowledgeBaseConfig,
) -> bool:
    return current.processing_dict() != updated.processing_dict()


async def get_or_create_knowledge_base_config(
    repository: KnowledgeBaseConfigRepository,
    knowledge_base_id: str,
    user_id: str,
    settings: Settings,
) -> KnowledgeBaseConfig:
    existing = await repository.get_by_knowledge_base_and_user(knowledge_base_id, user_id)
    if existing is not None:
        return existing
    return await repository.insert(
        build_default_knowledge_base_config(knowledge_base_id, user_id, settings)
    )


def apply_config_update(
    current: KnowledgeBaseConfig,
    update: object,
) -> KnowledgeBaseConfig:
    for section_name in ("processing", "retrieval", "generation"):
        section_update = getattr(update, section_name, None)
        if section_update is None:
            continue
        target = getattr(current, section_name)
        for field_name, value in section_update.model_dump(exclude_none=True).items():
            setattr(target, field_name, value)
    return current


async def validate_config_update_dependencies(
    update: KnowledgeBaseConfigUpdate,
    effective_config: KnowledgeBaseConfig,
    settings: Settings,
) -> None:
    """Validate only explicitly changed external-model settings before persistence."""
    requested_models: list[tuple[str, str]] = []
    if update.processing and update.processing.embedding_model_name:
        requested_models.append(("embedding", update.processing.embedding_model_name))
    if update.generation and update.generation.llm_model_name:
        requested_models.append(("LLM", update.generation.llm_model_name))

    if requested_models:
        try:
            available_models = await _fetch_ollama_model_names(settings)
        except httpx.HTTPError as exc:
            raise ConfigurationDependencyError("Ollama service unavailable") from exc
        for label, model_name in requested_models:
            if model_name not in available_models:
                raise ModelConfigurationError(
                    f"Configured {label} model was not found: {model_name}"
                )

    retrieval_update = update.retrieval
    rerank_was_explicitly_enabled = (
        retrieval_update is not None and retrieval_update.rerank_enabled is True
    )
    rerank_model_changed_while_enabled = (
        retrieval_update is not None
        and retrieval_update.rerank_model_name is not None
        and effective_config.retrieval.rerank_enabled
    )
    if not (rerank_was_explicitly_enabled or rerank_model_changed_while_enabled):
        return
    if not settings.rerank_base_url.strip() or not effective_config.retrieval.rerank_model_name:
        raise ModelConfigurationError("Rerank service and model must be configured before enabling rerank")
    try:
        await HttpRerankService(settings.rerank_base_url).rerank(
            "health check",
            ["health check"],
            effective_config.retrieval.rerank_model_name,
        )
    except RerankUnavailableError as exc:
        raise ConfigurationDependencyError("Rerank service unavailable") from exc


async def _fetch_ollama_model_names(settings: Settings) -> list[str]:
    base_url = settings.ollama_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=settings.health_check_timeout_seconds) as client:
        response = await client.get(f"{base_url}/api/tags")
        response.raise_for_status()
        payload = response.json()
    raw_models = payload.get("models") if isinstance(payload, dict) else []
    if not isinstance(raw_models, list):
        return []
    return [
        name
        for model in raw_models
        if isinstance(model, dict)
        for name in [model.get("name") or model.get("model")]
        if isinstance(name, str) and name
    ]
