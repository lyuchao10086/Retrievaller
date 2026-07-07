from typing import Protocol

import httpx


DEEPSEEK_API_KEY_NOT_CONFIGURED_MESSAGE = "DeepSeek API key is not configured"


class DeepSeekConfigurationError(RuntimeError):
    """DeepSeek API key 未配置。"""


class DeepSeekAPIError(RuntimeError):
    """DeepSeek API 请求失败。"""


class DeepSeekService(Protocol):
    """DeepSeek Chat Completions 调用接口。"""

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class HttpxDeepSeekService:
    """使用 httpx 调用 DeepSeek OpenAI 兼容接口。"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 120.0,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """调用 DeepSeek /chat/completions，并返回 assistant content。"""
        if not self.api_key:
            raise DeepSeekConfigurationError(
                DEEPSEEK_API_KEY_NOT_CONFIGURED_MESSAGE
            )

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            ) as client:
                response = await client.post(
                    "/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                    },
                )
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise DeepSeekAPIError(f"DeepSeek API request failed: {exc}") from exc

        if response.status_code >= 400:
            raise DeepSeekAPIError(
                f"DeepSeek API request failed with status "
                f"{response.status_code}: {response.text}"
            )

        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise DeepSeekAPIError("DeepSeek API returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content:
            raise DeepSeekAPIError("DeepSeek API returned empty content")
        return str(content).strip()
