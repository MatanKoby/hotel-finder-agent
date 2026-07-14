"""LLM scorer: JSON parsing on success, heuristic fallback (with a report) on failure.

Uses an injected fake backend — no network, no transport specifics (those are in
``test_nebius_endpoint.py``).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from hotel_finder.config import Settings
from hotel_finder.context import SearchContext
from hotel_finder.models import GeoPoint, Hotel
from hotel_finder.scoring.llm import LLMScorer, _hotel_payload, _OpenAIBackend


class _FakeBackend:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    async def complete(self, messages: list[dict[str, str]]) -> str:
        content = self._responses[self.calls]
        self.calls += 1
        return content


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"scorer": "llm", "llm_api_key": "test-key"}
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _valid_payload() -> str:
    return json.dumps(
        {
            "scores": [
                {"id": "h1", "value": 0.9, "location": 0.8, "character": 0.7,
                 "gem_signal": 0.6, "rationale": "great"},
                {"id": "h2", "value": 0.4, "location": 0.5, "character": 0.3,
                 "gem_signal": 0.1, "rationale": "meh"},
            ]
        }
    )


async def test_valid_json_is_scored(make_hotel: Callable[..., Hotel]) -> None:
    scorer = LLMScorer(_settings(), backend=_FakeBackend([_valid_payload()]))
    hotels = [make_hotel(id="h1", rating=8.0), make_hotel(id="h2", rating=6.0)]

    out = await scorer.score(hotels, SearchContext())

    by_id = {s.hotel.id: s for s in out}
    assert by_id["h1"].subscores["value"] == 0.9
    assert by_id["h1"].score == pytest.approx(0.83)  # 0.5*0.9 + 0.3*0.8 + 0.2*0.7
    assert by_id["h1"].rationale == "great"
    assert scorer.report.scorer == "llm"
    assert scorer.report.warnings == []


async def test_invalid_json_falls_back_to_heuristic(make_hotel: Callable[..., Hotel]) -> None:
    scorer = LLMScorer(_settings(), backend=_FakeBackend(["not json", "still not json"]))
    hotels = [make_hotel(id="h1", rating=8.0, price_per_night=100.0)]

    out = await scorer.score(hotels, SearchContext())

    assert len(out) == 1
    assert out[0].hotel.id == "h1"
    assert out[0].rationale  # heuristic produced a rationale
    assert scorer.report.scorer == "heuristic"
    assert scorer.report.warnings  # the fallback is recorded


async def test_omitted_hotel_falls_back(make_hotel: Callable[..., Hotel]) -> None:
    # Backend answers for h1 only; h2 missing -> fallback.
    partial = json.dumps(
        {"scores": [{"id": "h1", "value": 0.5, "location": 0.5,
                     "character": 0.5, "gem_signal": 0.5, "rationale": "x"}]}
    )
    scorer = LLMScorer(_settings(), backend=_FakeBackend([partial]))
    out = await scorer.score(
        [make_hotel(id="h1", rating=8.0), make_hotel(id="h2", rating=7.0)], SearchContext()
    )
    assert len(out) == 2
    assert scorer.report.scorer == "heuristic"


async def test_no_backend_configured_falls_back(make_hotel: Callable[..., Hotel]) -> None:
    scorer = LLMScorer(_settings(llm_api_key=""))  # nothing configured -> no backend
    out = await scorer.score([make_hotel(id="h1", rating=8.0)], SearchContext())
    assert len(out) == 1
    assert scorer.report.scorer == "heuristic"
    assert scorer.report.warnings


async def test_repair_retry_recovers(make_hotel: Callable[..., Hotel]) -> None:
    # First response is bad JSON; the repair retry returns valid scores.
    scorer = LLMScorer(_settings(), backend=_FakeBackend(["oops", _valid_payload()]))
    out = await scorer.score(
        [make_hotel(id="h1", rating=8.0), make_hotel(id="h2", rating=6.0)], SearchContext()
    )
    assert {s.hotel.id for s in out} == {"h1", "h2"}
    assert scorer.report.scorer == "llm"


def test_hotel_payload_grounds_location(make_hotel: Callable[..., Hotel]) -> None:
    center = GeoPoint(lat=41.385, lon=2.181)
    hotel = make_hotel(id="h1", area="El Born", location=GeoPoint(lat=41.386, lon=2.182))
    payload = _hotel_payload(hotel, center, "El Born")
    assert payload["coordinates"] == {"lat": 41.386, "lon": 2.182}
    assert isinstance(payload["distance_to_desired_km"], float)
    assert payload["distance_to_desired_km"] < 1.0  # ~150 m apart
    assert payload["in_desired_area"] is True


def test_hotel_payload_nulls_location_signals_when_absent(
    make_hotel: Callable[..., Hotel],
) -> None:
    payload = _hotel_payload(make_hotel(id="h1", area="Eixample"), None, None)
    assert payload["coordinates"] is None
    assert payload["distance_to_desired_km"] is None
    assert payload["in_desired_area"] is None


async def test_score_sends_distance_to_backend(make_hotel: Callable[..., Hotel]) -> None:
    backend = _FakeBackend([_valid_payload()])
    scorer = LLMScorer(_settings(), backend=backend)
    hotels = [
        make_hotel(id="h1", area="El Born", location=GeoPoint(lat=41.386, lon=2.182)),
        make_hotel(id="h2", area="Gràcia", location=GeoPoint(lat=41.403, lon=2.156)),
    ]
    context = SearchContext(center=GeoPoint(lat=41.385, lon=2.181), desired_area="El Born")

    captured: list[dict[str, str]] = []
    original = backend.complete

    async def _spy(messages: list[dict[str, str]]) -> str:
        captured.extend(messages)
        return await original(messages)

    backend.complete = _spy  # type: ignore[method-assign]
    await scorer.score(hotels, context)

    user_msg = next(m["content"] for m in captured if m["role"] == "user")
    assert "distance_to_desired_km" in user_msg and "in_desired_area" in user_msg


class _RecordingCompletions:
    """Captures the create() kwargs and returns a minimal completion-shaped object."""

    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        message = type("_Msg", (), {"content": '{"scores": []}'})()
        choice = type("_Choice", (), {"message": message})()
        return type("_Resp", (), {"choices": [choice]})()


def _capture_openai_create(
    **overrides: object,
) -> tuple[_OpenAIBackend, _RecordingCompletions]:
    """Build an ``_OpenAIBackend`` whose ``create()`` records its kwargs instead of hitting HTTP."""
    backend = _OpenAIBackend(_settings(**overrides))
    completions = _RecordingCompletions()
    backend.client.chat.completions = completions  # type: ignore[assignment]
    return backend, completions


async def test_disable_thinking_sends_extra_body() -> None:
    backend, completions = _capture_openai_create(llm_disable_thinking=True)
    await backend.complete([{"role": "user", "content": "hi"}])
    assert completions.kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


async def test_thinking_on_by_default_sends_no_extra_body() -> None:
    backend, completions = _capture_openai_create()  # llm_disable_thinking defaults to False
    await backend.complete([{"role": "user", "content": "hi"}])
    assert completions.kwargs["extra_body"] is None
