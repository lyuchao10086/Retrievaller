from fastapi.testclient import TestClient

from app.api.routes import health as health_route
from app.main import app


def test_health_returns_backend_and_dependency_status(monkeypatch):
    async def fake_check_dependencies():
        return {
            "mysql": {"status": "ok"},
            "redis": {"status": "ok"},
            "minio": {"status": "ok"},
            "milvus": {"status": "ok"},
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
        },
    }
