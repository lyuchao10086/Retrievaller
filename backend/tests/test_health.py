from fastapi.testclient import TestClient

from app.api.routes import health as health_route
from app.core.config import Settings
from app.main import app
from app.services.health import (
    check_deepseek_config,
    check_ollama_embedding,
)


def test_health_returns_backend_and_dependency_status(monkeypatch):
    async def fake_check_dependencies():
        return {
            "mysql": {"status": "ok"},
            "redis": {"status": "ok"},
            "minio": {"status": "ok"},
            "milvus": {"status": "ok"},
            "ollama_embedding": {"status": "ok", "model": "embed-model"},
            "ollama_llm": {"status": "warning", "model": "chat-model"},
            "deepseek_config": {"status": "warning", "detail": "DeepSeek API key is not configured"},
            "celery_config": {"status": "ok"},
        }

    monkeypatch.setattr(
        health_route,
        "check_dependencies_health",
        fake_check_dependencies,
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "backend": {"status": "ok"},
        "dependencies": {
            "mysql": {"status": "ok"},
            "redis": {"status": "ok"},
            "minio": {"status": "ok"},
            "milvus": {"status": "ok"},
            "ollama_embedding": {"status": "ok", "model": "embed-model"},
            "ollama_llm": {"status": "warning", "model": "chat-model"},
            "deepseek_config": {"status": "warning", "detail": "DeepSeek API key is not configured"},
            "celery_config": {"status": "ok"},
        },
    }


def test_deepseek_health_reports_warning_without_exposing_key():
    settings = Settings(deepseek_api_key="")

    payload = check_deepseek_config(settings)

    assert payload["status"] == "warning"
    assert "api key" in payload["detail"].lower()
    assert "deepseek_api_key" not in str(payload).lower()


def test_ollama_embedding_health_warns_when_configured_model_is_missing(monkeypatch):
    settings = Settings(
        ollama_base_url="http://ollama.test",
        embedding_model_name="missing-embed:latest",
    )

    async def fake_fetch_ollama_model_names(_settings):
        return ["qwen3:latest"]

    monkeypatch.setattr(
        "app.services.health._fetch_ollama_model_names",
        fake_fetch_ollama_model_names,
    )

    import asyncio

    result = asyncio.run(check_ollama_embedding(settings))

    assert result["status"] == "warning"
    assert result["model"] == "missing-embed:latest"
    assert "not found" in result["detail"].lower()
