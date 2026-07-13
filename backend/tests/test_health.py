from fastapi.testclient import TestClient
import pytest

from app.api.routes import health as health_route
from app.core.config import Settings
from app.main import app
from app.services.health import (
    check_deepseek_config,
    check_ollama_embedding,
    check_ollama_rerank,
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


def test_live_health_does_not_check_dependencies(monkeypatch):
    async def failing_check_dependencies():
        raise AssertionError("live probe must not check dependencies")

    monkeypatch.setattr(
        health_route,
        "check_dependencies_health",
        failing_check_dependencies,
    )

    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"backend": {"status": "ok"}}


@pytest.mark.parametrize(
    "unavailable_dependency",
    ("mysql", "redis", "minio", "milvus", "ollama_embedding", "ollama_llm"),
)
def test_ready_health_returns_503_when_a_required_dependency_is_unavailable(
    monkeypatch,
    unavailable_dependency,
):
    async def fake_check_dependencies():
        dependencies = {
            "mysql": {"status": "ok"},
            "redis": {"status": "ok"},
            "minio": {"status": "ok"},
            "milvus": {"status": "ok"},
            "ollama_embedding": {"status": "ok"},
            "ollama_llm": {"status": "ok"},
            "deepseek_config": {"status": "warning"},
            "celery_config": {"status": "ok"},
            "ollama_rerank": {"status": "warning"},
        }
        dependencies[unavailable_dependency] = {
            "status": "error",
            "code": "dependency_unreachable",
        }
        return dependencies

    monkeypatch.setattr(
        health_route,
        "check_dependencies_health",
        fake_check_dependencies,
    )

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["backend"]["status"] == "error"
    assert response.json()["unready_dependencies"] == [unavailable_dependency]


def test_ready_health_allows_optional_dependency_warnings(monkeypatch):
    async def fake_check_dependencies():
        return {
            "mysql": {"status": "ok"},
            "redis": {"status": "ok"},
            "minio": {"status": "ok"},
            "milvus": {"status": "ok"},
            "ollama_embedding": {"status": "ok"},
            "ollama_llm": {"status": "ok"},
            "deepseek_config": {"status": "warning"},
            "celery_config": {"status": "warning"},
            "ollama_rerank": {"status": "warning"},
        }

    monkeypatch.setattr(
        health_route,
        "check_dependencies_health",
        fake_check_dependencies,
    )

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json()["backend"]["status"] == "ok"


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


def test_rerank_health_uses_the_v1_rerank_protocol(monkeypatch):
    settings = Settings(
        rerank_base_url="http://rerank.test",
        rerank_model_name="rerank-model",
    )

    async def fake_request_rerank_health(_settings):
        return {"results": [{"index": 0, "relevance_score": 0.5}]}

    monkeypatch.setattr(
        "app.services.health._request_rerank_health",
        fake_request_rerank_health,
    )

    import asyncio

    result = asyncio.run(check_ollama_rerank(settings))

    assert result["status"] == "ok"
    assert result["model"] == "rerank-model"
    assert result["protocol"] == "/v1/rerank"
