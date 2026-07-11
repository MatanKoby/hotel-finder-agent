"""Thin client for the shared Nebius serverless endpoint (Ollama REST API, no API key).

The orchestrator run mode: this repo contacts a shared endpoint that speaks the **Ollama REST API**
(`GET /api/tags` for liveness + model discovery, `POST /api/chat` for completion), authenticated
with a bearer token. The single served model is auto-discovered unless one is configured. Mirrors
the sibling flight agent's endpoint pattern, but as a thin client (no Nebius-CLI lifecycle). See
`spec/scoring.md` and `spec/config.md`.
"""

from __future__ import annotations

from typing import Any

import httpx


class NebiusEndpointError(RuntimeError):
    """Raised when the endpoint is unreachable or serves no usable model."""


class NebiusEndpointClient:
    """Minimal Ollama-REST client: discover the model, then chat."""

    def __init__(
        self,
        url: str,
        token: str,
        model: str = "",
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._model = model
        self._timeout = timeout
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _get(self, path: str) -> httpx.Response:
        if self._client is not None:
            return await self._client.get(f"{self._url}{path}", headers=self._headers())
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.get(f"{self._url}{path}", headers=self._headers())

    async def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(f"{self._url}{path}", json=body, headers=self._headers())
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(f"{self._url}{path}", json=body, headers=self._headers())

    async def list_models(self) -> list[str]:
        """Model names the endpoint serves (also the liveness probe)."""
        response = await self._get("/api/tags")
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models") or []
        return [m["name"] for m in models if isinstance(m, dict) and m.get("name")]

    async def resolve_model(self) -> str:
        """The configured model, or the single served one auto-discovered via ``/api/tags``."""
        if self._model:
            return self._model
        models = await self.list_models()
        if not models:
            raise NebiusEndpointError("endpoint serves no models")
        return models[0]

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """One non-streaming JSON chat completion; returns the assistant message content."""
        model = await self.resolve_model()
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        response = await self._post("/api/chat", body)
        response.raise_for_status()
        payload = response.json()
        content = (payload.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise NebiusEndpointError("endpoint response had no message content")
        return content
