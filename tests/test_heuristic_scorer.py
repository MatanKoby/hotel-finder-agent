"""Heuristic scorer: determinism, score ranges, gem detection."""

from __future__ import annotations

from collections.abc import Callable

from hotel_finder.contracts import HotelQuery
from hotel_finder.models import Amenity, Hotel
from hotel_finder.scoring.heuristic import HeuristicScorer


def _gem_and_mainstream(make_hotel: Callable[..., Hotel]) -> list[Hotel]:
    gem = make_hotel(
        id="gem",
        name="Gem",
        rating=4.9,
        review_count=30,
        price_per_night=120.0,
        star_rating=3,
        amenities={Amenity.WIFI, Amenity.AC},
        description="charming",
    )
    mainstream = make_hotel(
        id="big",
        name="Big",
        rating=4.8,
        review_count=1500,
        price_per_night=120.0,
    )
    return [gem, mainstream]


async def test_deterministic(make_hotel: Callable[..., Hotel]) -> None:
    scorer = HeuristicScorer()
    query = HotelQuery(location="X")
    hotels = _gem_and_mainstream(make_hotel)
    first = await scorer.score(hotels, query)
    second = await scorer.score(hotels, query)
    assert [s.model_dump() for s in first] == [s.model_dump() for s in second]


async def test_scores_in_range_and_gem_signal(make_hotel: Callable[..., Hotel]) -> None:
    scorer = HeuristicScorer()
    scored = await scorer.score(_gem_and_mainstream(make_hotel), HotelQuery(location="X"))
    by_id = {s.hotel.id: s for s in scored}

    for item in scored:
        assert 0.0 <= item.score <= 1.0

    # Few reviews + high rating + good value -> stronger gem signal than the mainstream pick.
    assert by_id["gem"].subscores["gem_signal"] > by_id["big"].subscores["gem_signal"]
