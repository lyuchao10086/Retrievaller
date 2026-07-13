from typing import Protocol

import httpx


class EmbeddingService(Protocol):
    """文本向量化服务接口，方便后续替换成本地模型或远程 API。"""

    def embed_texts(
        self,
        texts: list[str],
        model_name: str | None = None,
    ) -> list[list[float]]:
        raise NotImplementedError


class OllamaEmbeddingService:
    """基于本地 Ollama embedding 模型的实现。"""

    def __init__(
        self,
        model_name: str,
        base_url: str,
        timeout_seconds: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def embed_texts(
        self,
        texts: list[str],
        model_name: str | None = None,
    ) -> list[list[float]]:
        """把文本列表转换成向量列表。"""
        if not texts:
            return []

        with httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = client.post(
                "/api/embed",
                    json={"model": model_name or self.model_name, "input": texts},
            )
            if response.status_code == 404:
                return [self._embed_one_with_legacy_api(client, text) for text in texts]

            response.raise_for_status()
            payload = response.json()

        embeddings = payload.get("embeddings")
        if embeddings is None:
            embedding = payload.get("embedding")
            embeddings = [] if embedding is None else [embedding]
        return [_to_float_list(embedding) for embedding in embeddings]

    def _embed_one_with_legacy_api(
        self,
        client: httpx.Client,
        text: str,
    ) -> list[float]:
        """兼容 Ollama 旧版 /api/embeddings 接口。"""
        response = client.post(
            "/api/embeddings",
            json={"model": self.model_name, "prompt": text},
        )
        response.raise_for_status()
        return _to_float_list(response.json()["embedding"])


def _to_float_list(values: list[float]) -> list[float]:
    return [float(value) for value in values]
