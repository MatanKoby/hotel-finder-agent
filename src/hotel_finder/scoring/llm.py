"""Opt-in LLM scorer with two transports, both contacted by this repo (see ``spec/scoring.md``).

- **Backend A (OpenAI-compatible):** the ``openai`` SDK against ``llm_base_url`` with an API key
  (eval/testing → Nebius Token Factory; also Groq/xAI/OpenRouter).
- **Backend B (Nebius serverless endpoint):** a thin Ollama-REST client, no API key, the single
  served model auto-discovered, with a brief cold-start retry (the orchestrator run mode).

The backend is chosen by ``llm_backend`` / which env vars are set. Either way the scorer asks for
one JSON object, validates it, retries once on bad JSON, and **falls back to the heuristic scorer**
on any failure — recording the effective scorer (and a warning) in :class:`ScoreReport` so the
pipeline can report it truthfully.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Protocol, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ConfigDict, ValidationError

from hotel_finder.config import Settings
from hotel_finder.context import SearchContext
from hotel_finder.models import Hotel
from hotel_finder.scoring.base import HotelScorer, ScoredHotel, ScoreReport, overall_score
from hotel_finder.scoring.heuristic import HeuristicScorer
from hotel_finder.scoring.nebius_endpoint import NebiusEndpointClient

logger = logging.getLogger(__name__)

_COLD_START_ATTEMPTS = 2  # the endpoint may be waking; retry the transport briefly
_COLD_START_DELAY = 1.5

_SYSTEM_PROMPT = (
    "You are a hotel analyst. Score each hotel on four axes, each a float in [0, 1]:\n"
    "- value: quality (rating/stars) relative to its price.\n"
    "- location: fit to the requested location/desired area.\n"
    "- character: distinctiveness and amenities (a memorable place scores higher).\n"
    "- gem_signal: a hidden gem — excellent for its price and under-the-radar "
    "(great rating with relatively few reviews).\n"
    'Return ONLY a JSON object: {"scores": [{"id": str, "value": num, "location": num, '
    '"character": num, "gem_signal": num, "rationale": str}]}. '
    "rationale is one short sentence. Include every hotel id exactly once."
)

Message = dict[str, str]


class _LLMItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    value: float
    location: float
    character: float
    gem_signal: float
    rationale: str = ""


class _LLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scores: list[_LLMItem]


class _ChatBackend(Protocol):
    """A transport that turns a chat into a single JSON string response."""

    async def complete(self, messages: list[Message]) -> str: ...


class _OpenAIBackend:
    """OpenAI-compatible chat completions (Nebius Token Factory, Groq, ...)."""

    def __init__(self, settings: Settings) -> None:
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "missing",
            timeout=settings.llm_timeout,
        )
        self._model = settings.llm_model

    async def complete(self, messages: list[Message]) -> str:
        response = await self.client.chat.completions.create(
            model=self._model,
            messages=cast("list[ChatCompletionMessageParam]", messages),
            response_format={"type": "json_object"},
            temperature=0,
        )
        return response.choices[0].message.content or ""


class _EndpointBackend:
    """Nebius serverless endpoint (Ollama REST), with a brief cold-start retry."""

    def __init__(self, settings: Settings, client: NebiusEndpointClient | None = None) -> None:
        self.client = client or NebiusEndpointClient(
            settings.nebius_endpoint_url,
            settings.nebius_endpoint_token,
            settings.nebius_endpoint_model,
            settings.llm_timeout,
        )

    async def complete(self, messages: list[Message]) -> str:
        last_exc: Exception | None = None
        for attempt in range(_COLD_START_ATTEMPTS):
            try:
                return await self.client.chat(messages)
            except Exception as exc:  # noqa: BLE001 — retried, then surfaced to the fallback
                last_exc = exc
                if attempt + 1 < _COLD_START_ATTEMPTS:
                    await asyncio.sleep(_COLD_START_DELAY)
        assert last_exc is not None
        raise last_exc


def _select_backend(settings: Settings) -> _ChatBackend | None:
    """Pick a backend from ``llm_backend`` / which credentials are configured."""
    choice = settings.llm_backend
    if choice == "auto":
        if settings.nebius_endpoint_url:
            choice = "endpoint"
        elif settings.llm_api_key:
            choice = "openai"
        else:
            return None
    if choice == "endpoint" and settings.nebius_endpoint_url:
        return _EndpointBackend(settings)
    if choice == "openai" and settings.llm_api_key:
        return _OpenAIBackend(settings)
    return None


def _hotel_payload(hotel: Hotel) -> dict[str, object]:
    return {
        "id": hotel.id,
        "name": hotel.name,
        "area": hotel.area,
        "price_per_night": hotel.price_per_night,
        "currency": hotel.currency,
        "price_band": hotel.price_band.value if hotel.price_band else None,
        "rating": hotel.rating,
        "review_count": hotel.review_count,
        "star_rating": hotel.star_rating,
        "amenities": sorted(a.value for a in hotel.amenities),
        "description": hotel.description,
    }


def _parse(content: str) -> list[_LLMItem]:
    return _LLMResponse.model_validate(json.loads(content)).scores


class LLMScorer:
    """Scores via an LLM (either transport), with a heuristic fallback on any failure."""

    def __init__(
        self,
        settings: Settings,
        fallback: HotelScorer | None = None,
        backend: _ChatBackend | None = None,
    ) -> None:
        self._settings = settings
        self._fallback: HotelScorer = fallback or HeuristicScorer()
        self._backend = backend if backend is not None else _select_backend(settings)
        self._report = ScoreReport(scorer="llm")

    @property
    def report(self) -> ScoreReport:
        return self._report

    async def score(self, hotels: list[Hotel], context: SearchContext) -> list[ScoredHotel]:
        if not hotels:
            self._report = ScoreReport(scorer="llm")
            return []
        if self._backend is None:
            return await self._fall_back(hotels, context, "no LLM backend configured")

        try:
            items = await self._request_scores(hotels, context)
        except Exception as exc:  # noqa: BLE001 — any failure should degrade, not crash
            return await self._fall_back(hotels, context, f"LLM scorer failed ({exc})")

        by_id = {item.id: item for item in items}
        if any(hotel.id not in by_id for hotel in hotels):
            return await self._fall_back(hotels, context, "LLM response omitted some hotels")

        self._report = ScoreReport(scorer="llm")
        return [_to_scored(hotel, by_id[hotel.id]) for hotel in hotels]

    async def _fall_back(
        self, hotels: list[Hotel], context: SearchContext, reason: str
    ) -> list[ScoredHotel]:
        logger.warning("%s; using heuristic scorer", reason)
        self._report = ScoreReport(
            scorer="heuristic", warnings=[f"{reason}; used the heuristic scorer"]
        )
        return await self._fallback.score(hotels, context)

    async def _request_scores(
        self, hotels: list[Hotel], context: SearchContext
    ) -> list[_LLMItem]:
        assert self._backend is not None
        payload = {
            "query": {
                "location": context.location_label,
                "desired_area": context.desired_area,
                "must_have_amenities": sorted(a.value for a in context.filters.must_have_amenities),
                "price_min": context.filters.price_min,
                "price_max": context.filters.price_max,
            },
            "hotels": [_hotel_payload(h) for h in hotels],
        }
        messages: list[Message] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ]

        content = await self._backend.complete(messages)
        try:
            return _parse(content)
        except (json.JSONDecodeError, ValidationError):
            # One repair retry: show the bad output and re-state the required shape.
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": "That was not valid. Respond with ONLY the JSON object described.",
                }
            )
            return _parse(await self._backend.complete(messages))


def _to_scored(hotel: Hotel, item: _LLMItem) -> ScoredHotel:
    subscores = {
        "value": round(item.value, 3),
        "location": round(item.location, 3),
        "character": round(item.character, 3),
        "gem_signal": round(item.gem_signal, 3),
    }
    overall = overall_score(item.value, item.location, item.character)
    return ScoredHotel(
        hotel=hotel,
        score=round(overall, 3),
        subscores=subscores,
        rationale=item.rationale,
    )
