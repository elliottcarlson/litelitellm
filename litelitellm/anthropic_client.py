"""
Anthropic HTTP client - httpx-based, no SDK dependency.

Provides stream_to_anthropic(), call_anthropic(), and acompletion_anthropic() for the shim.
"""

import contextvars
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from . import config

_request_api_key: contextvars.ContextVar[str] = contextvars.ContextVar("_request_api_key", default="")
_request_passthrough_headers: contextvars.ContextVar[Optional[Dict]] = contextvars.ContextVar("_request_passthrough_headers", default=None)

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    return _client


def _build_headers(api_key: str, anthropic_version: str, passthrough_headers: Optional[Dict] = None) -> Dict:
    headers: Dict[str, str] = {}
    if passthrough_headers:
        headers.update(passthrough_headers)
    headers["x-api-key"] = api_key
    headers["anthropic-version"] = anthropic_version
    headers["content-type"] = "application/json"
    return headers


async def stream_to_anthropic(
    request_data: Dict,
    api_key: str,
    anthropic_version: str,
    passthrough_headers: Optional[Dict] = None,
    query_string: str = "",
) -> AsyncIterator[bytes]:
    request_data["stream"] = True
    url = f"{config.ANTHROPIC_API_URL}/v1/messages"
    if query_string:
        url = f"{url}?{query_string}"
    headers = _build_headers(api_key, anthropic_version, passthrough_headers)
    client = _get_client()
    async with client.stream("POST", url, json=request_data, headers=headers) as resp:
        if resp.status_code != 200:
            body = await resp.aread()
            yield b"event: error\ndata: " + body + b"\n\n"
            return
        async for chunk in resp.aiter_bytes():
            yield chunk


async def call_anthropic(
    request_data: Dict,
    api_key: str,
    anthropic_version: str,
    passthrough_headers: Optional[Dict] = None,
    query_string: str = "",
) -> Dict:
    request_data["stream"] = False
    url = f"{config.ANTHROPIC_API_URL}/v1/messages"
    if query_string:
        url = f"{url}?{query_string}"
    headers = _build_headers(api_key, anthropic_version, passthrough_headers)
    client = _get_client()
    resp = await client.post(url, json=request_data, headers=headers)
    resp.raise_for_status()
    return resp.json()


class ContentBlock:
    def __init__(self, data: Dict):
        self._data = data
        for k, v in data.items():
            setattr(self, k, v)

    def model_dump(self) -> Dict:
        return dict(self._data)


class AnthropicResponse:
    def __init__(self, data: Dict):
        self._data = data
        self.id = data.get("id", "")
        self.type = data.get("type", "message")
        self.role = data.get("role", "assistant")
        self.model = data.get("model", "")
        self.stop_reason = data.get("stop_reason")
        self.stop_sequence = data.get("stop_sequence")
        self.usage = data.get("usage", {})
        raw_content = data.get("content", [])
        self.content = [ContentBlock(b) if isinstance(b, dict) else b for b in raw_content]

    def model_dump(self) -> Dict:
        return dict(self._data)


async def acompletion_anthropic(
    model: str,
    messages: List[Dict],
    tools: Optional[List[Dict]] = None,
    **kwargs,
) -> AnthropicResponse:
    api_key = kwargs.pop("api_key", None) or _request_api_key.get() or config.ANTHROPIC_API_KEY
    if not api_key:
        raise ValueError("No API key available")

    request_data: Dict[str, Any] = {"model": model, "messages": messages}
    if tools:
        request_data["tools"] = tools
    for param in ("max_tokens", "temperature", "top_p", "top_k", "system", "stop_sequences", "metadata"):
        if param in kwargs:
            request_data[param] = kwargs[param]
    if "max_tokens" not in request_data:
        request_data["max_tokens"] = 16384

    anthropic_version = kwargs.pop("anthropic_version", "2023-06-01")
    raw = await call_anthropic(request_data, api_key, anthropic_version, _request_passthrough_headers.get())
    return AnthropicResponse(raw)
