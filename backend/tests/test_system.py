from fastapi.testclient import TestClient

from app.main import app


def test_system_config_returns_safe_runtime_settings_without_secrets():
    response = TestClient(app).get("/api/system/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["provider"] == "ollama"
    assert "local_llm_model" in payload["llm"]
    assert "embedding_model_name" in payload["embedding"]
    assert "embedding_dimension" in payload["embedding"]
    assert payload["document_processing"]["mode"] == "celery"
    assert payload["document_processing"]["supported_file_types"] == [
        ".txt",
        ".md",
        ".markdown",
    ]
    assert payload["rerank"]["enabled"] is False
    assert "deepseek_api_key" not in str(payload).lower()
    assert "minio_secret_key" not in str(payload).lower()
