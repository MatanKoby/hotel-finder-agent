"""Heuristic scorer: determinism, score ranges, gem detection."""

from __future__ import annotations

from collections.abc import Callable

from hotel_finder.context import SearchContext
from hotel_finder.models import Amenity, Hotel
from hotel_finder.scoring.heuristic import HeuristicScorer


def _gem_and_mainstream(make_hotel: Callable[..., Hotel]) -> list[Hotel]:
    gem = make_hotel(
        id="gem",
        name="Gem",
        rating=9.6,
        review_count=30,
        price_per_night=120.0,
        star_rating=3,
        amenities={Amenity.WIFI, Amenity.AC},
        description="charming",
    )
    mainstream = make_hotel(
        id="big",
        name="Big",
        rating=9.4,
        review_count=1500,
        price_per_night=120.0,
    )
    return [gem, mainstream]


async def test_deterministic(make_hotel: Callable[..., Hotel]) -> None:
    scorer = HeuristicScorer()
    context = SearchContext()
    hotels = _gem_and_mainstream(make_hotel)
    first = await scorer.score(hotels, context)
    second = await scorer.score(hotels, context)
    assert [s.model_dump() for s in first] == [s.model_dump() for s in second]


async def test_scores_in_range_and_gem_signal(make_hotel: Callable[..., Hotel]) -> None:
    scorer = HeuristicScorer()
    scored = await scorer.score(_gem_and_mainstream(make_hotel), SearchContext())
    by_id = {s.hotel.id: s for s in scored}

    for item in scored:
        assert 0.0 <= item.score <= 1.0

    # Few reviews + high rating + good value -> stronger gem signal than the mainstream pick.
    assert by_id["gem"].subscores["gem_signal"] > by_id["big"].subscores["gem_signal"]


async def test_area_affinity_grades_without_a_center(make_hotel: Callable[..., Hotel]) -> None:
    # No center: the desired-area string must still separate an exact match, a partial word overlap,
    # and a different neighbourhood (which floors below the no-signal neutral of 0.6).
    hotels = [
        make_hotel(id="exact", area="El Born"),
        make_hotel(id="partial", area="Born Riverside"),
        make_hotel(id="miss", area="Gràcia"),
    ]
    scored = await HeuristicScorer().score(hotels, SearchContext(desired_area="El Born"))
    loc = {s.hotel.id: s.subscores["location"] for s in scored}

    assert loc["exact"] == 1.0
    assert 0.35 < loc["partial"] < 1.0
    assert loc["miss"] == 0.35
    assert loc["exact"] > loc["partial"] > loc["miss"]
