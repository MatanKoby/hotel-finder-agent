"""End-to-end pipeline over the mock provider + heuristic scorer (fully offline)."""

from __future__ import annotations

from datetime import date

from hotel_finder.config import Settings
from hotel_finder.contracts import Filters, HotelSearchRequest, LensName, Place, Stay
from hotel_finder.pipeline import search, search_sync


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"scorer": "heuristic", "enabled_providers": ["mock"]}
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _stay() -> Stay:
    return Stay(check_in=date(2026, 8, 1), check_out=date(2026, 8, 4))  # 3 nights


async def test_end_to_end_produces_all_lenses() -> None:
    request = HotelSearchRequest(place=Place(city="Barcelona"))
    response = await search(request, _settings())

    assert response.request_id == request.request_id
    assert response.status == "ok"
    assert response.warnings == []
    assert response.meta.candidates_found == 14
    assert response.meta.scorer == "heuristic"
    assert response.meta.widened is False

    for lens in LensName:
        assert lens in response.lenses

    gem_ids = [p.hotel.id for p in response.lenses[LensName.HIDDEN_GEMS]]
    assert "bcn-011" in gem_ids  # the planted hidden gem surfaces

    bands = {p.hotel.price_band for p in response.lenses[LensName.STRATIFIED_BEST]}
    assert len(bands) >= 3  # coverage across price tiers

    # Coordinates are surfaced for the downstream itinerary agent.
    assert all(p.coordinates is not None for p in response.lenses[LensName.OVERALL_STANDOUTS])

    # No stay -> content-only, no priced offers.
    assert all(not p.offers for picks in response.lenses.values() for p in picks)


async def test_resolved_echoes_place_and_stay() -> None:
    request = HotelSearchRequest(place=Place(city="Barcelona"), stay=_stay())
    response = await search(request, _settings())

    assert response.resolved.city == "Barcelona"
    assert response.resolved.check_in == date(2026, 8, 1)
    assert response.resolved.currency == "EUR"


async def test_offers_present_with_stay_within_budget() -> None:
    request = HotelSearchRequest(
        place=Place(city="Barcelona"), stay=_stay(), filters=Filters(price_max=500.0)
    )
    response = await search(request, _settings())

    assert response.status == "ok"
    priced = [p for picks in response.lenses.values() for p in picks if p.offers]
    assert priced  # at least some picks carry offers
    for pick in priced:
        offer = pick.offers[0]
        assert offer.over_budget is False
        assert offer.per_night == pick.hotel.price_per_night
        assert offer.total == round(pick.hotel.price_per_night * 3, 2)


async def test_budget_too_low_fallback_degrades_and_flags_offers() -> None:
    request = HotelSearchRequest(
        place=Place(city="Barcelona"), stay=_stay(), filters=Filters(price_max=62.0)
    )
    response = await search(request, _settings(min_candidates=8))

    assert response.meta.widened is True
    assert response.status == "degraded"
    assert any("within EUR 62" in w for w in response.warnings)

    all_offers = [o for picks in response.lenses.values() for p in picks for o in p.offers]
    assert any(o.over_budget for o in all_offers)  # the fallback flags the over-budget rates


async def test_bounded_agency_widening_content_only() -> None:
    # A tight price cap leaves only 2 candidates (< min_candidates) -> widening kicks in.
    request = HotelSearchRequest(place=Place(city="Barcelona"), filters=Filters(price_max=62.0))
    response = await search(request, _settings(min_candidates=8))

    assert response.meta.widened is True
    assert response.meta.candidates_after_filter >= 8
    assert response.status == "degraded"  # over-budget hotels surfaced


async def test_lenses_subset_is_honored() -> None:
    request = HotelSearchRequest(
        place=Place(city="Barcelona"), lenses=[LensName.OVERALL_STANDOUTS]
    )
    response = await search(request, _settings())

    assert set(response.lenses) == {LensName.OVERALL_STANDOUTS}


async def test_llm_without_credentials_reports_heuristic_fallback() -> None:
    # scorer=llm but no LLM backend configured -> the pipeline reports the effective scorer.
    request = HotelSearchRequest(place=Place(city="Barcelona"))
    response = await search(request, _settings(scorer="llm"))

    assert response.meta.scorer == "heuristic"
    assert response.status == "degraded"
    assert any("heuristic" in w for w in response.warnings)


def test_search_sync_returns_envelope() -> None:
    request = HotelSearchRequest(place=Place(city="Barcelona"))
    response = search_sync(request, _settings())

    assert response.request_id == request.request_id
    assert response.lenses
