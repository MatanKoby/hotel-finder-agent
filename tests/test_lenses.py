"""The three lens projections over a scored set."""

from __future__ import annotations

from collections.abc import Callable

from hotel_finder.models import Hotel, PriceBand
from hotel_finder.scoring.base import ScoredHotel
from hotel_finder.stages import lenses


def _scored(
    make_hotel: Callable[..., Hotel],
    hotel_id: str,
    score: float,
    band: PriceBand,
    gem: float = 0.0,
) -> ScoredHotel:
    return ScoredHotel(
        hotel=make_hotel(id=hotel_id, price_band=band),
        score=score,
        subscores={"gem_signal": gem},
    )


def test_stratified_best_one_per_band(make_hotel: Callable[..., Hotel]) -> None:
    scored = [
        _scored(make_hotel, "a", 0.5, PriceBand.BUDGET),
        _scored(make_hotel, "b", 0.9, PriceBand.BUDGET),
        _scored(make_hotel, "c", 0.7, PriceBand.LUXURY),
    ]
    out = lenses.stratified_best(scored, per_band=1)
    assert [s.hotel.id for s in out] == ["b", "c"]  # budget winner, then luxury (band order)


def test_overall_standouts_top_k(make_hotel: Callable[..., Hotel]) -> None:
    scored = [
        _scored(make_hotel, "a", 0.5, PriceBand.BUDGET),
        _scored(make_hotel, "b", 0.9, PriceBand.BUDGET),
        _scored(make_hotel, "c", 0.7, PriceBand.LUXURY),
    ]
    out = lenses.overall_standouts(scored, k=2)
    assert [s.hotel.id for s in out] == ["b", "c"]


def test_hidden_gems_threshold(make_hotel: Callable[..., Hotel]) -> None:
    scored = [
        _scored(make_hotel, "a", 0.5, PriceBand.BUDGET, gem=0.6),
        _scored(make_hotel, "b", 0.9, PriceBand.BUDGET, gem=0.1),
    ]
    out = lenses.hidden_gems(scored, k=5)
    assert [s.hotel.id for s in out] == ["a"]
