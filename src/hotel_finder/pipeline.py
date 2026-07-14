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
    Diagnostics,
    HotelSearchRequest,
    HotelSearchResponse,
    Intent,
    LensName,
    Pick,
    RateOffer,
    ResolvedQuery,
)
from hotel_finder.models import GeoPoint, Hotel
from hotel_finder.providers.base import HotelProvider
from hotel_finder.providers.registry import get_providers
from hotel_finder.scoring import make_scorer
from hotel_finder.scoring.base import ScoredHotel
from hotel_finder.stages import lenses
from hotel_finder.stages.anchor import anchor_envelope, find_anchor
from hotel_finder.stages.dedupe import dedupe
from hotel_finder.stages.explain import to_picks
from hotel_finder.stages.filtering import FilterCriteria, hard_filter
from hotel_finder.stages.shortlist import shortlist
from hotel_finder.utils.geocode import make_geocoder

logger = logging.getLogger(__name__)


async def search(
    request: HotelSearchRequest, settings: Settings | None = None
) -> HotelSearchResponse:
    """Run the pipeline for ``request`` and return a ``HotelSearchResponse`` envelope."""
    settings = settings or Settings()
    warnings: list[str] = []

    resolved, request, filter_center = await _resolve(request, settings, warnings)

    providers = get_providers(settings.enabled_providers, settings)
    candidates = await _gather(providers, request, warnings)
    candidates = dedupe(candidates)
    candidates_found = len(candidates)
    candidates = [_with_price_band(h, settings) for h in candidates]

    # The hard-filter base is the request's own filters; ANCHOR intent tightens it to the peers of
    # a named hotel (and re-centres ranking on it). Both feed the same widening + scoring path.
    base = _base_criteria(request, filter_center, settings)
    if request.intent is Intent.ANCHOR:
        candidates, base, resolved = _apply_anchor(
            request, candidates, base, resolved, settings, warnings
        )

    context = SearchContext(
        center=resolved.center,  # the desired point: explicit centre, geocoded area, or the anchor
        desired_area=request.place.desired_area,
        location_label=resolved.city or request.place.text,
        filters=request.filters,
    )

    filtered, widened = _filter_with_widening(candidates, base, settings)
    short = shortlist(filtered, context, settings.shortlist_size)

    scorer = make_scorer(settings)
    scored = await scorer.score(short, context)
    warnings.extend(scorer.report.warnings)  # e.g. an LLM -> heuristic fallback

    offers_by_id = {s.hotel.id: _offers_for(s.hotel, request) for s in scored}
    lenses_out = _build_lenses(scored, request, offers_by_id, resolved.center)
    _apply_budget_fallback(lenses_out, request, candidates, warnings)

    diagnostics = Diagnostics(
        providers_used=[p.name for p in providers],
        candidates_found=candidates_found,
        candidates_after_filter=len(filtered),
        shortlisted=len(short),
        scorer=scorer.report.scorer,  # the scorer that actually ran (heuristic on fallback)
        widened=widened,
    )
    return HotelSearchResponse(
        request_id=request.request_id,
        agent_status=_status(lenses_out, warnings),
        warnings=warnings,
        resolved=resolved,
        lenses=lenses_out,
        diagnostics=diagnostics,
    )


def search_sync(
    request: HotelSearchRequest, settings: Settings | None = None
) -> HotelSearchResponse:
    """Blocking convenience wrapper around :func:`search` for non-async callers.

    Not usable from inside a running event loop (use ``await search(...)`` there).
    """
    return asyncio.run(search(request, settings))


async def _resolve(
    request: HotelSearchRequest, settings: Settings, warnings: list[str]
) -> tuple[ResolvedQuery, HotelSearchRequest, GeoPoint | None]:
    """Resolve ``Place`` into what the pipeline actually searches.

    Structured fields pass through. When only ``text`` is given, geocode it (non-fatally) into a
    ``center`` + ``city`` + ``country_code``. Returns three things: the ``ResolvedQuery`` (for the
    response, whose ``center`` is the **desired point** the results are ranked around), an
    **effective request** whose ``place`` carries the resolved fields so providers discover against
    them, and the **filter centre** (used only for the hard radius filter).

    Two distinct "centres" fall out of a search:

    * the **filter centre** — an explicit ``place.center`` or a geocoded free-text ``place`` —
      bounds the hard radius filter and drives provider discovery;
    * the **desired point** — the filter centre when there is one, otherwise a geocoded
      ``desired_area`` — is what proximity ranking and ``distance_to_desired_km`` measure against. A
      geocoded neighbourhood is a soft ranking bias, never a hard radius, so it is kept off the
      filter centre.
    """
    place = request.place
    center = place.center  # the filter centre (explicit, or geocoded free text below)
    city = place.city
    country_code = place.country_code

    if center is None and not city and place.text:
        result = None
        failed = False
        try:
            result = await make_geocoder(settings).geocode(place.text)
        except Exception as exc:  # noqa: BLE001 — geocoding must never crash a search
            failed = True
            logger.warning("geocoding %r failed: %s", place.text, exc)
            warnings.append(f"geocoding {place.text!r} failed ({exc}); results may be broad")
        if result is not None:
            center = GeoPoint(lat=result.lat, lon=result.lon)
            city = result.city or city
            country_code = result.country_code or country_code
        elif not failed:
            warnings.append(f"could not geocode {place.text!r}; results may be broad")

    effective_place = place.model_copy(
        update={"center": center, "city": city, "country_code": country_code}
    )
    effective_request = request.model_copy(update={"place": effective_place})

    # The desired point: the filter centre if we have one, else a geocoded neighbourhood (soft bias,
    # so a miss is silent — it just falls back to the area-string signal, never a warning/degrade).
    desired_point = center
    if desired_point is None and place.desired_area and settings.geocode_desired_area:
        desired_point = await _geocode_desired_area(
            place.desired_area, city, country_code, settings
        )

    stay = request.stay
    resolved = ResolvedQuery(
        center=desired_point,
        city=city,
        area=place.desired_area,
        check_in=stay.check_in if stay else None,
        check_out=stay.check_out if stay else None,
        currency=stay.currency if stay else None,
    )
    return resolved, effective_request, center


async def _geocode_desired_area(
    desired_area: str, city: str | None, country_code: str | None, settings: Settings
) -> GeoPoint | None:
    """Geocode a neighbourhood into a ranking point, disambiguated by city/country. Never fatal."""
    query = ", ".join(part for part in (desired_area, city, country_code) if part)
    try:
        result = await make_geocoder(settings).geocode(query)
    except Exception as exc:  # noqa: BLE001 — a soft bias must never crash a search
        logger.warning("geocoding desired_area %r failed: %s", query, exc)
        return None
    return GeoPoint(lat=result.lat, lon=result.lon) if result is not None else None


def _apply_anchor(
    request: HotelSearchRequest,
    candidates: list[Hotel],
    base: FilterCriteria,
    resolved: ResolvedQuery,
    settings: Settings,
    warnings: list[str],
) -> tuple[list[Hotel], FilterCriteria, ResolvedQuery]:
    """Constrain the search to peers of ``request.anchor_hotel`` (see ``stages/anchor.py``).

    Locate the anchor among the discovered candidates, exclude it (it is the reference, not a
    recommendation), and tighten ``base`` to its peer envelope; ranking re-centres on the anchor by
    making it ``resolved.center``. On any miss (anchor not found, or too thin to constrain peers),
    warn and return the zone inputs unchanged so the search degrades to a broad area search rather
    than returning nothing — never crashes (see ``contract.md`` → Error philosophy).
    """
    where = resolved.city or request.place.text or "the requested area"
    anchor = find_anchor(candidates, request.anchor_hotel or "")
    if anchor is None:
        warnings.append(
            f"anchor hotel {request.anchor_hotel!r} not found near {where}; "
            "searched the area broadly instead"
        )
        return candidates, base, resolved

    envelope = anchor_envelope(anchor, settings)
    if envelope.is_empty():
        warnings.append(
            f"anchor hotel {anchor.name!r} has too little data to match peers; "
            "searched the area broadly instead"
        )
        return candidates, base, resolved

    peers = [h for h in candidates if h.id != anchor.id]
    if anchor.location is not None:
        resolved = resolved.model_copy(update={"center": anchor.location})
    return peers, envelope.to_criteria(base), resolved


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
    base: FilterCriteria,
    settings: Settings,
) -> tuple[list[Hotel], bool]:
    """Hard-filter against ``base``; if too few survive, relax **soft** constraints with a capped
    retry.

    Must-have amenities and quality bounds (min_star / min_guest_rating) are never relaxed. Widening
    grows the area radius every step; on price it is **gentle** — the middle steps widen the price
    band by ``widen_price_factor`` (so a slightly-too-low budget recovers with hotels near it, not
    the whole city), and only the **final** step drops the bounds entirely to guarantee the
    budget-too-low fallback still returns something. A fixed loop with a cap, not the LLM deciding.
    """
    filtered = hard_filter(candidates, base)
    if len(filtered) >= settings.min_candidates:
        return filtered, False

    radius = base.radius_km
    last = settings.max_widen_steps - 1
    for step in range(settings.max_widen_steps):
        if radius is not None:
            radius += settings.widen_radius_km
        price_min, price_max = _widened_price(base, step, last, settings.widen_price_factor)
        relaxed = FilterCriteria(
            must_have_amenities=base.must_have_amenities,
            price_min=price_min,
            price_max=price_max,
            min_star=base.min_star,
            min_guest_rating=base.min_guest_rating,
            center=base.center,
            radius_km=radius,
        )
        filtered = hard_filter(candidates, relaxed)
        if len(filtered) >= settings.min_candidates:
            break
    return filtered, True


def _widened_price(
    base: FilterCriteria, step: int, last: int, factor: float
) -> tuple[float | None, float | None]:
    """Price bounds for a widening step: keep (step 0), widen the band (middle), drop (final)."""
    if step >= last:
        return None, None  # final step: no price discipline, so the fallback always recovers
    if step == 0:
        return base.price_min, base.price_max  # first widen the area only, price untouched
    scale = 1.0 + factor * step
    price_max = base.price_max * scale if base.price_max is not None else None
    price_min = base.price_min / scale if base.price_min is not None else None
    return price_min, price_max


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
    center: GeoPoint | None,
) -> dict[LensName, list[Pick]]:
    k = request.picks_per_lens
    wanted = request.lenses if request.lenses is not None else list(LensName)
    out: dict[LensName, list[Pick]] = {}
    if LensName.STRATIFIED_BEST in wanted:
        out[LensName.STRATIFIED_BEST] = to_picks(
            lenses.stratified_best(scored, per_band=1),
            offers_by_id,
            center,
            LensName.STRATIFIED_BEST,
        )
    if LensName.OVERALL_STANDOUTS in wanted:
        out[LensName.OVERALL_STANDOUTS] = to_picks(
            lenses.overall_standouts(scored, k), offers_by_id, center, LensName.OVERALL_STANDOUTS
        )
    if LensName.HIDDEN_GEMS in wanted:
        out[LensName.HIDDEN_GEMS] = to_picks(
            lenses.hidden_gems(scored, k), offers_by_id, center, LensName.HIDDEN_GEMS
        )
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
    over = any(
        pick.price_per_night is not None and pick.price_per_night > price_max
        for picks in lenses_out.values()
        for pick in picks
    )
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
