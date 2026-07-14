"""ANCHOR intent: locate a named hotel and return its peers (stages/anchor.py + pipeline wiring)."""

from __future__ import annotations

from hotel_finder.config import Settings
from hotel_finder.contracts import (
    Filters,
    HotelSearchRequest,
    Intent,
    LensName,
    Place,
)
from hotel_finder.models import GeoPoint, Hotel
from hotel_finder.pipeline import search
from hotel_finder.stages.anchor import AnchorEnvelope, anchor_envelope, find_anchor
from hotel_finder.stages.filtering import FilterCriteria


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"scorer": "heuristic", "enabled_providers": ["mock"]}
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _hotel(hid: str, name: str, **fields: object) -> Hotel:
    return Hotel(id=hid, source="test", name=name, **fields)  # type: ignore[arg-type]


# --- find_anchor -----------------------------------------------------------------------------


def test_find_anchor_exact_normalized_name() -> None:
    hotels = [_hotel("1", "Hotel Arts Barcelona"), _hotel("2", "Ritz Madrid")]
    assert find_anchor(hotels, "hotel arts barcelona") is hotels[0]  # case/accent insensitive


def test_find_anchor_unique_containment_either_direction() -> None:
    hotels = [_hotel("1", "Hotel Arts Barcelona"), _hotel("2", "Ritz Madrid")]
    assert find_anchor(hotels, "Hotel Arts") is hotels[0]  # query is a substring of the name
    assert find_anchor(hotels, "Ritz Madrid Gran Vía") is hotels[1]  # name is a substring of query


def test_find_anchor_ambiguous_containment_returns_none() -> None:
    hotels = [_hotel("1", "Plaza North"), _hotel("2", "Plaza South")]
    assert find_anchor(hotels, "Plaza") is None  # two matches -> refuse to guess


def test_find_anchor_no_match_or_empty_returns_none() -> None:
    hotels = [_hotel("1", "Hotel Arts Barcelona")]
    assert find_anchor(hotels, "Nonexistent") is None
    assert find_anchor(hotels, "   ") is None


# --- anchor_envelope -------------------------------------------------------------------------


def test_anchor_envelope_full_data() -> None:
    anchor = _hotel(
        "a",
        "Anchor",
        location=GeoPoint(lat=41.39, lon=2.16),
        price_per_night=200.0,
        star_rating=4,
        rating=9.0,
    )
    env = anchor_envelope(anchor, _settings())
    assert env.center == GeoPoint(lat=41.39, lon=2.16)
    assert env.radius_km == 3.0
    assert env.price_min == 120.0 and env.price_max == 320.0  # 200 * 0.6 / 1.6
    assert env.min_star == 3  # 4 - 1 tolerance
    assert env.min_guest_rating == 8.0  # 9.0 - 1.0 tolerance
    assert not env.is_empty()


def test_anchor_envelope_partial_and_empty() -> None:
    price_only = anchor_envelope(_hotel("a", "Anchor", price_per_night=100.0), _settings())
    assert price_only.center is None and price_only.min_star is None
    assert price_only.price_min == 60.0 and price_only.price_max == 160.0
    assert not price_only.is_empty()

    bare = anchor_envelope(_hotel("a", "Anchor"), _settings())  # no geo/price/star/rating
    assert bare.is_empty()


def test_envelope_to_criteria_tightens_never_loosens() -> None:
    env = AnchorEnvelope(
        center=GeoPoint(lat=41.39, lon=2.16),
        radius_km=3.0,
        price_min=120.0,
        price_max=320.0,
        min_star=3,
        min_guest_rating=8.0,
    )
    # The request already caps price harder and floors stars higher; the stricter bound wins.
    base = FilterCriteria(price_max=250.0, min_star=4, center=None, radius_km=None)
    merged = env.to_criteria(base)
    assert merged.price_min == 120.0  # from the envelope
    assert merged.price_max == 250.0  # the request's tighter ceiling wins
    assert merged.min_star == 4  # the request's higher floor wins
    assert merged.min_guest_rating == 8.0  # from the envelope
    assert merged.center == env.center and merged.radius_km == 3.0  # anchor re-centres ranking


# --- end to end over the mock provider -------------------------------------------------------

_ANCHOR = "Diagonal Upscale Suites"  # bcn-007: 260 EUR, 4-star, 9.2, Eixample
_EXPECTED_PEERS = {"Barceloneta Beach Inn", "El Born Riverside"}


async def test_anchor_returns_peers_within_the_envelope() -> None:
    request = HotelSearchRequest(
        place=Place(city="Barcelona"), intent=Intent.ANCHOR, anchor_hotel=_ANCHOR
    )
    # min_candidates=1 so the envelope holds (no widening) and the peer set is exact.
    response = await search(request, _settings(min_candidates=1))

    assert response.agent_status == "ok"  # a clean anchor resolution does not warn/degrade
    assert response.warnings == []
    assert response.diagnostics.widened is False
    # Ranking re-centres on the anchor's coordinates.
    assert response.resolved.center == GeoPoint(lat=41.3925, lon=2.1605)

    all_picks = [p for picks in response.lenses.values() for p in picks]
    names = {p.name for p in all_picks}
    assert _ANCHOR not in names  # the anchor is the reference, never returned as its own peer
    assert names == _EXPECTED_PEERS  # only the in-envelope peers survive
    # overall_standouts surfaces both peers.
    assert {p.name for p in response.lenses[LensName.OVERALL_STANDOUTS]} == _EXPECTED_PEERS

    for pick in all_picks:
        assert pick.price_per_night is not None and 156.0 <= pick.price_per_night <= 416.0
        assert pick.star_rating is not None and pick.star_rating >= 3
        assert pick.rating is not None and pick.rating >= 8.2
        assert pick.distance_to_desired_km is not None and pick.distance_to_desired_km <= 3.0


async def test_anchor_matches_on_partial_name() -> None:
    request = HotelSearchRequest(
        place=Place(city="Barcelona"), intent=Intent.ANCHOR, anchor_hotel="Diagonal Upscale"
    )
    response = await search(request, _settings(min_candidates=1))
    names = {p.name for picks in response.lenses.values() for p in picks}
    assert names == _EXPECTED_PEERS


async def test_anchor_respects_request_filters() -> None:
    # The request caps price below the anchor's window; the tighter ceiling still applies to peers.
    request = HotelSearchRequest(
        place=Place(city="Barcelona"),
        intent=Intent.ANCHOR,
        anchor_hotel=_ANCHOR,
        filters=Filters(price_max=200.0),
    )
    response = await search(request, _settings(min_candidates=1))
    for pick in (p for picks in response.lenses.values() for p in picks):
        assert pick.price_per_night is not None and pick.price_per_night <= 200.0


async def test_anchor_not_found_falls_back_to_broad_zone() -> None:
    request = HotelSearchRequest(
        place=Place(city="Barcelona"),
        intent=Intent.ANCHOR,
        anchor_hotel="Ritz Nonexistent Palace",
    )
    response = await search(request, _settings())

    assert response.agent_status == "degraded"
    assert any("not found" in w and "Ritz Nonexistent Palace" in w for w in response.warnings)
    assert response.diagnostics.candidates_found == 14  # nothing excluded; the whole city searched
    names = {p.name for picks in response.lenses.values() for p in picks}
    # A broad search surfaces hotels an anchor envelope would have excluded (e.g. the budget gem).
    assert "Gothic Quiet Courtyard" in names
