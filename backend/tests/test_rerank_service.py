import asyncio

import httpx

from app.services.rerank_service import HttpRerankService


def test_rerank_service_orders_results_by_relevance_score():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/rerank"
        payload = __import__("json").loads(request.content)
        assert payload["documents"] == ["first", "second"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.42},
                ]
            },
        )

    service = HttpRerankService(
        base_url="http://rerank.test",
        transport=httpx.MockTransport(handler),
    )
    results = asyncio.run(
        service.rerank("question", ["first", "second"], "rerank-model")
    )

    assert [(item.index, item.score) for item in results] == [(1, 0.91), (0, 0.42)]
