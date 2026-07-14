"""Unit tests for the explain stage: flat ``Pick`` projection, provider photo, and distance."""

from __future__ import annotations

from hotel_finder.contracts import LensName
from hotel_finder.models import GeoPoint, Hotel, PriceBand
from hotel_finder.scoring.base import ScoredHotel
from hotel_finder.stages.explain import to_pick
from hotel_finder.utils.geo import haversine

_SAGRADA = GeoPoint(lat=41.4036, lon=2.1744)
_HOTEL_POINT = GeoPoint(lat=41.3851, lon=2.1734)  # ~2 km south


def _scored(location: GeoPoint | None, image_url: str | None = None) -> ScoredHotel:
    hotel = Hotel(
        id="h1",
        source="mock",
        name="Test Hotel",
        location=location,
        image_url=image_url,
    )
    return ScoredHotel(hotel=hotel, score=0.5, subscores={"value": 0.5})


def test_distance_to_desired_km_computed_when_center_and_location_present() -> None:
    scored = _scored(_HOTEL_POINT)
    pick = to_pick(scored, [], _SAGRADA)

    assert pick.distance_to_desired_km == round(haversine(_HOTEL_POINT, _SAGRADA), 2)
    assert pick.distance_to_desired_km is not None
    assert 1.5 < pick.distance_to_desired_km < 3.0  # ~2 km, sanity bound


def test_distance_is_none_without_center() -> None:
    pick = to_pick(_scored(_HOTEL_POINT), [], None)
    assert pick.distance_to_desired_km is None


def test_distance_is_none_when_hotel_has_no_coordinates() -> None:
    pick = to_pick(_scored(None), [], _SAGRADA)
    assert pick.distance_to_desired_km is None


def test_image_url_passes_through_from_hotel() -> None:
    pick = to_pick(_scored(_HOTEL_POINT, image_url="https://img/1.jpg"), [], _SAGRADA)
    assert pick.image_url == "https://img/1.jpg"

    assert to_pick(_scored(_HOTEL_POINT), [], _SAGRADA).image_url is None  # None when absent


def _rated(rationale: str, band: PriceBand | None = None) -> ScoredHotel:
    hotel = Hotel(id="h1", source="mock", name="Test Hotel", price_band=band)
    return ScoredHotel(hotel=hotel, score=0.7, subscores={"value": 0.7}, rationale=rationale)


def test_stratified_lens_appends_price_tier() -> None:
    pick = to_pick(_rated("great value", PriceBand.BUDGET), [], None, LensName.STRATIFIED_BEST)
    assert pick.rationale == "great value (best of the budget tier)"


def test_hidden_gems_lens_adds_gem_framing_only_when_missing() -> None:
    added = to_pick(_rated("quiet and central"), [], None, LensName.HIDDEN_GEMS)
    assert added.rationale == "Hidden gem: quiet and central"
    # Already gem-framed: don't double it up.
    kept = to_pick(_rated("a likely hidden gem"), [], None, LensName.HIDDEN_GEMS)
    assert kept.rationale == "a likely hidden gem"


def test_overall_lens_leaves_rationale_untouched() -> None:
    pick = to_pick(_rated("strong all round"), [], None, LensName.OVERALL_STANDOUTS)
    assert pick.rationale == "strong all round"
