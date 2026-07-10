"""End-to-end pipeline over the mock provider + heuristic scorer (fully offline)."""

from __future__ import annotations

from hotel_finder.config import Settings
from hotel_finder.contracts import HotelQuery, LensName
from hotel_finder.pipeline import recommend


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"scorer": "heuristic", "enabled_providers": ["mock"]}
    base.update(overrides)
    return Settings(_env_file=None, **base)


async def test_end_to_end_produces_all_lenses() -> None:
    recs = await recommend(HotelQuery(location="Barcelona"), _settings())

    assert recs.meta.candidates_found == 14
    assert recs.meta.scorer == "heuristic"
    assert recs.meta.widened is False

    for lens in LensName:
        assert lens in recs.lenses

    gem_ids = [p.hotel.id for p in recs.lenses[LensName.HIDDEN_GEMS]]
    assert "bcn-011" in gem_ids  # the planted hidden gem surfaces

    bands = {p.hotel.price_band for p in recs.lenses[LensName.STRATIFIED_BEST]}
    assert len(bands) >= 3  # coverage across price tiers

    # Coordinates are surfaced for the downstream itinerary agent.
    assert all(p.coordinates is not None for p in recs.lenses[LensName.OVERALL_STANDOUTS])


async def test_bounded_agency_widening() -> None:
    # A tight price cap leaves only 2 candidates (< min_candidates) -> widening kicks in.
    query = HotelQuery(location="Barcelona", price_max=62.0)
    recs = await recommend(query, _settings(min_candidates=8))

    assert recs.meta.widened is True
    assert recs.meta.candidates_after_filter >= 8
