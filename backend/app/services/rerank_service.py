from dataclasses import dataclass

import httpx


class RerankUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RerankResult:
    index: int
    score: float


class HttpRerankService:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def rerank(
        self,
        query: str,
        documents: list[str],
        model_name: str,
    ) -> list[RerankResult]:
        if not documents:
            return []
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    "/v1/rerank",
                    json={
                        "model": model_name,
                        "query": query,
                        "documents": documents,
                    },
                )
                response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RerankUnavailableError("Rerank service unavailable") from exc

        raw_results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            raise RerankUnavailableError("Rerank service returned invalid results")
        results: list[RerankResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            score = item.get("relevance_score")
            if not isinstance(index, int) or not isinstance(score, (int, float)):
                continue
            if 0 <= index < len(documents):
                results.append(RerankResult(index=index, score=float(score)))
        if len(results) != len(documents):
            raise RerankUnavailableError("Rerank service returned incomplete results")
        return sorted(results, key=lambda item: item.score, reverse=True)
