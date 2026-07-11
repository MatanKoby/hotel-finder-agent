"""LLM scorer: JSON parsing/validation on success, heuristic fallback on failure.

Uses a stubbed OpenAI-compatible client — no network calls.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from hotel_finder.config import Settings
from hotel_finder.context import SearchContext
from hotel_finder.models import Hotel
from hotel_finder.scoring.llm import LLMScorer


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    async def create(self, **kwargs: Any) -> _FakeCompletion:
        content = self._responses[self.calls]
        self.calls += 1
        return _FakeCompletion(content)


class _FakeChat:
    def __init__(self, responses: list[str]) -> None:
        self.completions = _FakeCompletions(responses)


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.chat = _FakeChat(responses)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"scorer": "llm", "llm_api_key": "test-key"}
    base.update(overrides)
    return Settings(_env_file=None, **base)


async def test_valid_json_is_scored(make_hotel: Callable[..., Hotel]) -> None:
    scorer = LLMScorer(_settings())
    hotels = [make_hotel(id="h1", rating=4.0), make_hotel(id="h2", rating=3.0)]
    payload = json.dumps(
        {
            "scores": [
                {
                    "id": "h1",
                    "value": 0.9,
                    "location": 0.8,
                    "character": 0.7,
                    "gem_signal": 0.6,
                    "rationale": "great",
                },
                {
                    "id": "h2",
                    "value": 0.4,
                    "location": 0.5,
                    "character": 0.3,
                    "gem_signal": 0.1,
                    "rationale": "meh",
                },
            ]
        }
    )
    scorer._client = _FakeClient([payload])  # type: ignore[assignment]

    out = await scorer.score(hotels, SearchContext())
    by_id = {s.hotel.id: s for s in out}
    assert by_id["h1"].subscores["value"] == 0.9
    assert by_id["h1"].score == pytest.approx(0.83)  # 0.5*0.9 + 0.3*0.8 + 0.2*0.7
    assert by_id["h1"].rationale == "great"


async def test_invalid_json_falls_back_to_heuristic(make_hotel: Callable[..., Hotel]) -> None:
    scorer = LLMScorer(_settings())
    hotels = [make_hotel(id="h1", rating=4.0, price_per_night=100.0)]
    scorer._client = _FakeClient(["not json", "still not json"])  # type: ignore[assignment]

    out = await scorer.score(hotels, SearchContext())
    assert len(out) == 1
    assert out[0].hotel.id == "h1"
    assert out[0].rationale  # heuristic produced a rationale


async def test_missing_api_key_falls_back(make_hotel: Callable[..., Hotel]) -> None:
    scorer = LLMScorer(_settings(llm_api_key=""))
    # Empty response list: the client must NOT be called (it would IndexError if it were).
    scorer._client = _FakeClient([])  # type: ignore[assignment]

    out = await scorer.score([make_hotel(id="h1", rating=4.0)], SearchContext())
    assert len(out) == 1
