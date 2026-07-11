"""Nebius serverless endpoint (Ollama REST) client + LLM backend selection (all offline)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from hotel_finder.config import Settings
from hotel_finder.context import SearchContext
from hotel_finder.models import Hotel
from hotel_finder.scoring.llm import (
    LLMScorer,
    _EndpointBackend,
    _OpenAIBackend,
    _select_backend,
)
from hotel_finder.scoring.nebius_endpoint import NebiusEndpointClient, NebiusEndpointError


def _endpoint_handler(chat_content: str) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})
        if request.url.path.endswith("/api/chat"):
            body = json.loads(request.content)
            assert body["model"] == "qwen2.5:7b"  # auto-discovered
            assert body["stream"] is False
            return httpx.Response(
                200, json={"message": {"role": "assistant", "content": chat_content}}
            )
        return httpx.Response(404)

    return handler


async def test_client_auto_discovers_model_and_chats() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(_endpoint_handler('{"scores":[]}')))
    endpoint = NebiusEndpointClient("https://ep.test", "tok", client=client)

    assert await endpoint.resolve_model() == "qwen2.5:7b"
    content = await endpoint.chat([{"role": "user", "content": "hi"}])
    await client.aclose()

    assert content == '{"scores":[]}'


async def test_client_no_models_raises() -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json={"models": []}))
    client = httpx.AsyncClient(transport=transport)
    endpoint = NebiusEndpointClient("https://ep.test", "tok", client=client)
    with pytest.raises(NebiusEndpointError):
        await endpoint.resolve_model()
    await client.aclose()


def test_backend_selection_auto_and_forced() -> None:
    assert _select_backend(Settings(_env_file=None)) is None  # nothing configured
    assert isinstance(_select_backend(Settings(_env_file=None, llm_api_key="k")), _OpenAIBackend)
    endpoint_only = Settings(_env_file=None, nebius_endpoint_url="https://ep")
    assert isinstance(_select_backend(endpoint_only), _EndpointBackend)

    # auto prefers the endpoint when both are set; force selects otherwise.
    both = Settings(_env_file=None, llm_api_key="k", nebius_endpoint_url="https://ep")
    assert isinstance(_select_backend(both), _EndpointBackend)
    forced = Settings(
        _env_file=None, llm_api_key="k", nebius_endpoint_url="https://ep", llm_backend="openai"
    )
    assert isinstance(_select_backend(forced), _OpenAIBackend)


async def test_scorer_over_endpoint_backend(make_hotel: Callable[..., Hotel]) -> None:
    scores = {
        "scores": [
            {"id": "h1", "value": 0.9, "location": 0.8, "character": 0.7,
             "gem_signal": 0.6, "rationale": "nice"}
        ]
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(_endpoint_handler(json.dumps(scores))))
    backend = _EndpointBackend(
        Settings(_env_file=None, nebius_endpoint_url="https://ep.test"),
        client=NebiusEndpointClient("https://ep.test", "tok", client=client),
    )
    scorer = LLMScorer(Settings(_env_file=None), backend=backend)

    out = await scorer.score([make_hotel(id="h1", rating=8.0)], SearchContext())
    await client.aclose()

    assert len(out) == 1
    assert out[0].subscores["value"] == 0.9
    assert scorer.report.scorer == "llm"
