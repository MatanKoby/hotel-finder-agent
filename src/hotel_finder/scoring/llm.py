"""Opt-in LLM scorer over any OpenAI-compatible endpoint.

Defaults target Groq's free tier (configurable to xAI Grok, OpenRouter, etc. via ``Settings``).
It asks the model to rate the shortlist on the fuzzy axes, validates the JSON with Pydantic, and
**falls back to the heuristic scorer** on any error — missing key, network failure, bad JSON, or
an incomplete answer — so a flaky or absent model never breaks a request.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ConfigDict, ValidationError

from hotel_finder.config import Settings
from hotel_finder.context import SearchContext
from hotel_finder.models import Hotel
from hotel_finder.scoring.base import HotelScorer, ScoredHotel, overall_score
from hotel_finder.scoring.heuristic import HeuristicScorer

logger = logging.getLogger(__name__)

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
    """Scores via an OpenAI-compatible chat model, with a heuristic fallback on any failure."""

    def __init__(self, settings: Settings, fallback: HotelScorer | None = None) -> None:
        self._settings = settings
        self._fallback: HotelScorer = fallback or HeuristicScorer()
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "missing",
            timeout=settings.llm_timeout,
        )

    async def score(self, hotels: list[Hotel], context: SearchContext) -> list[ScoredHotel]:
        if not hotels:
            return []
        if not self._settings.llm_api_key:
            logger.warning("no LLM_API_KEY set; using heuristic scorer")
            return await self._fallback.score(hotels, context)

        try:
            items = await self._request_scores(hotels, context)
        except Exception as exc:  # noqa: BLE001 — any failure should degrade, not crash
            logger.warning("LLM scoring failed (%s); falling back to heuristic", exc)
            return await self._fallback.score(hotels, context)

        by_id = {item.id: item for item in items}
        if any(hotel.id not in by_id for hotel in hotels):
            logger.warning("LLM response omitted some hotels; falling back to heuristic")
            return await self._fallback.score(hotels, context)

        return [_to_scored(hotel, by_id[hotel.id]) for hotel in hotels]

    async def _request_scores(
        self, hotels: list[Hotel], context: SearchContext
    ) -> list[_LLMItem]:
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
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ]

        content = await self._complete(messages)
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
            return _parse(await self._complete(messages))

    async def _complete(self, messages: list[ChatCompletionMessageParam]) -> str:
        response = await self._client.chat.completions.create(
            model=self._settings.llm_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        return response.choices[0].message.content or ""


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
