from typing import Protocol

import httpx


LOCAL_LLM_UNAVAILABLE_MESSAGE = "Local LLM service unavailable"


class LocalLLMUnavailableError(RuntimeError):
    """本地大模型服务不可用时抛出，API 层会转换成明确错误响应。"""


class LocalLLMService(Protocol):
    """本地大模型调用接口，便于后续替换实现。"""

    async def generate_answer(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class OllamaLocalLLMService:
    """通过 Ollama HTTP API 调用本地 qwen3 等大模型。"""

    def __init__(
        self,
        model_name: str,
        base_url: str,
        timeout_seconds: float = 180.0,
    ):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def generate_answer(self, system_prompt: str, user_prompt: str) -> str:
        """调用 Ollama /api/chat，并返回 assistant message content。"""
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            ) as client:
                response = await client.post(
                    "/api/chat",
                    json={
                        "model": self.model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise LocalLLMUnavailableError(LOCAL_LLM_UNAVAILABLE_MESSAGE) from exc

        payload = response.json()
        message = payload.get("message") or {}
        content = message.get("content") or payload.get("response")
        if not content:
            raise LocalLLMUnavailableError(LOCAL_LLM_UNAVAILABLE_MESSAGE)
        return str(content).strip()
