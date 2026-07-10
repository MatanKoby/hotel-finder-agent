"""The deterministic orchestrator — ``recommend()``.

Sequences the fixed stages in plain code (no LLM-chosen control flow): gather → dedupe → derive
price bands → hard-filter with bounded-agency widening → shortlist → score once → lenses →
explain. This is the agent's single public entry point.
"""

from __future__ import annotations

import asyncio
import logging

from hotel_finder.config import Settings
from hotel_finder.contracts import (
    HotelQuery,
    LensName,
    Pick,
    RecommendationMeta,
    Recommendations,
)
from hotel_finder.models import Hotel
from hotel_finder.providers.base import HotelProvider
from hotel_finder.providers.registry import get_providers
from hotel_finder.scoring import make_scorer
from hotel_finder.scoring.base import ScoredHotel
from hotel_finder.stages import lenses
from hotel_finder.stages.dedupe import dedupe
from hotel_finder.stages.explain import to_picks
from hotel_finder.stages.filtering import FilterCriteria, hard_filter
from hotel_finder.stages.shortlist import shortlist

logger = logging.getLogger(__name__)


async def recommend(query: HotelQuery, settings: Settings | None = None) -> Recommendations:
    """Produce lens-projected hotel recommendations for ``query``."""
    settings = settings or Settings()
    providers = get_providers(settings.enabled_providers)

    candidates = await _gather(providers, query)
    candidates = dedupe(candidates)
    candidates_found = len(candidates)
    candidates = [_with_price_band(h, settings) for h in candidates]

    filtered, widened = _filter_with_widening(candidates, query, settings)
    short = shortlist(filtered, query, settings.shortlist_size)

    scorer = make_scorer(settings)
    scored = await scorer.score(short, query)

    meta = RecommendationMeta(
        providers_used=[p.name for p in providers],
        candidates_found=candidates_found,
        candidates_after_filter=len(filtered),
        shortlisted=len(short),
        scorer=settings.scorer,
        widened=widened,
    )
    return Recommendations(
        query_id=query.id,
        lenses=_build_lenses(scored, query),
        meta=meta,
    )


async def _gather(providers: list[HotelProvider], query: HotelQuery) -> list[Hotel]:
    """Fan out to providers in parallel; a provider that errors is logged and skipped."""
    results = await asyncio.gather(
        *(provider.search(query) for provider in providers),
        return_exceptions=True,
    )
    hotels: list[Hotel] = []
    for provider, result in zip(providers, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("provider %s failed: %s", provider.name, result)
            continue
        hotels.extend(result)
    return hotels


def _with_price_band(hotel: Hotel, settings: Settings) -> Hotel:
    """Backfill a missing price band from the price using configured thresholds."""
    if hotel.price_band is None and hotel.price_per_night is not None:
        band = settings.price_band_for(hotel.price_per_night)
        return hotel.model_copy(update={"price_band": band})
    return hotel


def _filter_with_widening(
    candidates: list[Hotel], query: HotelQuery, settings: Settings
) -> tuple[list[Hotel], bool]:
    """Hard-filter; if too few survive, relax soft constraints with a capped retry.

    Must-have amenities are never relaxed (they're hard by definition). Widening grows the area
    radius and, on later steps, drops the price bounds. This is a fixed loop with a cap, not the
    LLM choosing its next move.
    """
    base = FilterCriteria(
        must_have_amenities=frozenset(query.must_have_amenities),
        price_min=query.price_min,
        price_max=query.price_max,
        center=query.center,
        radius_km=settings.widen_radius_km if query.center is not None else None,
    )
    filtered = hard_filter(candidates, base)
    if len(filtered) >= settings.min_candidates:
        return filtered, False

    radius = base.radius_km
    for step in range(settings.max_widen_steps):
        if radius is not None:
            radius += settings.widen_radius_km
        relaxed = FilterCriteria(
            must_have_amenities=base.must_have_amenities,
            price_min=base.price_min if step == 0 else None,
            price_max=base.price_max if step == 0 else None,
            center=base.center,
            radius_km=radius,
        )
        filtered = hard_filter(candidates, relaxed)
        if len(filtered) >= settings.min_candidates:
            break
    return filtered, True


def _build_lenses(scored: list[ScoredHotel], query: HotelQuery) -> dict[LensName, list[Pick]]:
    k = query.picks_per_lens
    return {
        LensName.STRATIFIED_BEST: to_picks(lenses.stratified_best(scored, per_band=1)),
        LensName.OVERALL_STANDOUTS: to_picks(lenses.overall_standouts(scored, k)),
        LensName.HIDDEN_GEMS: to_picks(lenses.hidden_gems(scored, k)),
    }
