"""The deterministic orchestrator — ``search()`` — and the thin ``search_sync()`` wrapper.

Sequences the fixed stages in plain code (no LLM-chosen control flow): resolve → gather → dedupe →
derive price bands → hard-filter with bounded-agency widening → shortlist → score once → lenses →
explain. It returns a ``HotelSearchResponse`` **envelope**: data problems become ``warnings`` +
``status``, never exceptions (see ``contract.md`` → Error philosophy). This is the submodule's
single public entry point.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Literal

from hotel_finder.config import Settings
from hotel_finder.context import SearchContext
from hotel_finder.contracts import (
    HotelSearchRequest,
    HotelSearchResponse,
    LensName,
    Pick,
    RateOffer,
    RecommendationMeta,
    ResolvedQuery,
)
from hotel_finder.models import GeoPoint, Hotel
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


async def search(
    request: HotelSearchRequest, settings: Settings | None = None
) -> HotelSearchResponse:
    """Run the pipeline for ``request`` and return a ``HotelSearchResponse`` envelope."""
    settings = settings or Settings()
    warnings: list[str] = []

    resolved = _resolve(request, warnings)
    context = SearchContext(
        center=resolved.center,
        desired_area=request.place.desired_area,
        location_label=request.place.city or request.place.text,
        filters=request.filters,
    )

    providers = get_providers(settings.enabled_providers, settings)
    candidates = await _gather(providers, request, warnings)
    candidates = dedupe(candidates)
    candidates_found = len(candidates)
    candidates = [_with_price_band(h, settings) for h in candidates]

    filtered, widened = _filter_with_widening(candidates, request, resolved.center, settings)
    short = shortlist(filtered, context, settings.shortlist_size)

    scorer = make_scorer(settings)
    scored = await scorer.score(short, context)

    offers_by_id = {s.hotel.id: _offers_for(s.hotel, request) for s in scored}
    lenses_out = _build_lenses(scored, request, offers_by_id)
    _apply_budget_fallback(lenses_out, request, candidates, warnings)

    meta = RecommendationMeta(
        providers_used=[p.name for p in providers],
        candidates_found=candidates_found,
        candidates_after_filter=len(filtered),
        shortlisted=len(short),
        scorer=settings.scorer,
        widened=widened,
    )
    return HotelSearchResponse(
        request_id=request.request_id,
        status=_status(lenses_out, warnings),
        warnings=warnings,
        resolved=resolved,
        lenses=lenses_out,
        meta=meta,
    )


def search_sync(
    request: HotelSearchRequest, settings: Settings | None = None
) -> HotelSearchResponse:
    """Blocking convenience wrapper around :func:`search` for non-async callers.

    Not usable from inside a running event loop (use ``await search(...)`` there).
    """
    return asyncio.run(search(request, settings))


def _resolve(request: HotelSearchRequest, warnings: list[str]) -> ResolvedQuery:
    """Resolve ``Place`` into what the pipeline searched. Structured passthrough for M1a;
    geocoding of free-text places lands in M1c (until then, warn and proceed broadly)."""
    place = request.place
    if place.center is None and not place.city and place.text:
        warnings.append(
            f"free-text place {place.text!r} was not geocoded (not yet supported); "
            "results may be broad"
        )
    stay = request.stay
    return ResolvedQuery(
        center=place.center,
        city=place.city,
        check_in=stay.check_in if stay else None,
        check_out=stay.check_out if stay else None,
        currency=stay.currency if stay else None,
    )


async def _gather(
    providers: list[HotelProvider], request: HotelSearchRequest, warnings: list[str]
) -> list[Hotel]:
    """Fan out to providers in parallel; a provider that errors warns and is skipped, not fatal."""
    results = await asyncio.gather(
        *(provider.search(request) for provider in providers),
        return_exceptions=True,
    )
    hotels: list[Hotel] = []
    for provider, result in zip(providers, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("provider %s failed: %s", provider.name, result)
            warnings.append(f"provider {provider.name} unavailable: {result}")
            continue
        hotels.extend(result)
    return hotels


def _with_price_band(hotel: Hotel, settings: Settings) -> Hotel:
    """Backfill a missing price band from the price using configured thresholds."""
    if hotel.price_band is None and hotel.price_per_night is not None:
        band = settings.price_band_for(hotel.price_per_night)
        return hotel.model_copy(update={"price_band": band})
    return hotel


def _base_criteria(
    request: HotelSearchRequest, center: GeoPoint | None, settings: Settings
) -> FilterCriteria:
    filters = request.filters
    radius = None
    if center is not None:
        radius = request.place.radius_km
        if radius is None:
            radius = settings.widen_radius_km
    return FilterCriteria(
        must_have_amenities=frozenset(filters.must_have_amenities),
        price_min=filters.price_min,
        price_max=filters.price_max,
        min_star=filters.min_star,
        min_guest_rating=filters.min_guest_rating,
        center=center,
        radius_km=radius,
    )


def _filter_with_widening(
    candidates: list[Hotel],
    request: HotelSearchRequest,
    center: GeoPoint | None,
    settings: Settings,
) -> tuple[list[Hotel], bool]:
    """Hard-filter; if too few survive, relax **soft** constraints with a capped retry.

    Must-have amenities and quality bounds (min_star / min_guest_rating) are never relaxed.
    Widening grows the area radius (step 0) and then drops the price bounds (step 1+). This is a
    fixed loop with a cap, not the LLM choosing its next move.
    """
    base = _base_criteria(request, center, settings)
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
            min_star=base.min_star,
            min_guest_rating=base.min_guest_rating,
            center=base.center,
            radius_km=radius,
        )
        filtered = hard_filter(candidates, relaxed)
        if len(filtered) >= settings.min_candidates:
            break
    return filtered, True


def _offers_for(hotel: Hotel, request: HotelSearchRequest) -> list[RateOffer]:
    """Read-only offers for a hotel. Content-only (no ``stay``) yields no offers.

    A provider that fetched real rates leaves normalized offer dicts in ``hotel.raw["offers"]``
    (e.g. LiteAPI's cheapest-refundable + cheapest-non-refundable). Otherwise a single offer is
    derived from the provider's ``price_per_night`` (the mock path). Either way the budget flag and
    an explicit ``refundable`` filter are applied here, once.
    """
    stay = request.stay
    if stay is None:
        return []

    raw_offers = hotel.raw.get("offers")
    if raw_offers:
        offers = [RateOffer(**offer) for offer in raw_offers]
    elif hotel.price_per_night is not None:
        nights = (stay.check_out - stay.check_in).days
        offers = [
            RateOffer(
                total=round(hotel.price_per_night * nights, 2),
                currency=hotel.currency or stay.currency,
                per_night=hotel.price_per_night,
                board=None,
                refundable=True,  # no cancellation data on this path
            )
        ]
    else:
        return []

    price_max = request.filters.price_max
    want_refundable = request.filters.refundable
    result: list[RateOffer] = []
    for offer in offers:
        basis = offer.per_night if offer.per_night is not None else offer.total
        flagged = offer.model_copy(
            update={"over_budget": price_max is not None and basis > price_max}
        )
        if want_refundable is not None and flagged.refundable != want_refundable:
            continue
        result.append(flagged)
    return result


def _build_lenses(
    scored: list[ScoredHotel],
    request: HotelSearchRequest,
    offers_by_id: dict[str, list[RateOffer]],
) -> dict[LensName, list[Pick]]:
    k = request.picks_per_lens
    wanted = request.lenses if request.lenses is not None else list(LensName)
    out: dict[LensName, list[Pick]] = {}
    if LensName.STRATIFIED_BEST in wanted:
        out[LensName.STRATIFIED_BEST] = to_picks(
            lenses.stratified_best(scored, per_band=1), offers_by_id
        )
    if LensName.OVERALL_STANDOUTS in wanted:
        out[LensName.OVERALL_STANDOUTS] = to_picks(
            lenses.overall_standouts(scored, k), offers_by_id
        )
    if LensName.HIDDEN_GEMS in wanted:
        out[LensName.HIDDEN_GEMS] = to_picks(lenses.hidden_gems(scored, k), offers_by_id)
    return out


def _apply_budget_fallback(
    lenses_out: dict[LensName, list[Pick]],
    request: HotelSearchRequest,
    candidates: list[Hotel],
    warnings: list[str],
) -> None:
    """If the returned picks include over-budget hotels (only possible once price widening kicked
    in), record the budget-too-low fallback: warn with the price floor. Offers are already flagged
    ``over_budget`` in :func:`_offers_for`."""
    price_max = request.filters.price_max
    if price_max is None:
        return
    picked = {pick.hotel.id: pick.hotel for picks in lenses_out.values() for pick in picks}
    over = [
        h
        for h in picked.values()
        if h.price_per_night is not None and h.price_per_night > price_max
    ]
    if not over:
        return
    prices = [h.price_per_night for h in candidates if h.price_per_night is not None]
    if not prices:
        return
    currency = _dominant_currency(request, candidates)
    warnings.append(
        f"no hotels within {currency} {price_max:.0f}/night; "
        f"cheapest is {currency} {min(prices):.0f}/night"
    )


def _dominant_currency(request: HotelSearchRequest, candidates: list[Hotel]) -> str:
    if request.stay is not None:
        return request.stay.currency
    seen = Counter(h.currency for h in candidates if h.currency)
    if seen:
        return seen.most_common(1)[0][0]
    return "EUR"


def _status(
    lenses_out: dict[LensName, list[Pick]], warnings: list[str]
) -> Literal["ok", "empty", "degraded"]:
    if not any(picks for picks in lenses_out.values()):
        return "empty"
    return "degraded" if warnings else "ok"
