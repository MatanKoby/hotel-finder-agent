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


def test_stratified_best_falls_back_to_star_tiers_without_bands(
    make_hotel: Callable[..., Hotel],
) -> None:
    # No price bands (content-only, no rates): stratify by star tier, highest first, best per tier.
    scored = [
        ScoredHotel(hotel=make_hotel(id="a", star_rating=5), score=0.6),
        ScoredHotel(hotel=make_hotel(id="b", star_rating=5), score=0.9),
        ScoredHotel(hotel=make_hotel(id="c", star_rating=3), score=0.7),
    ]
    out = lenses.stratified_best(scored, per_band=1)
    assert [s.hotel.id for s in out] == ["b", "c"]  # 5-star winner first, then the 3-star tier


def test_stratified_best_star_fallback_capped_to_band_count(
    make_hotel: Callable[..., Hotel],
) -> None:
    # Five distinct star tiers but no bands: cap at len(PriceBand)=4 picks (drop the lowest tier).
    scored = [
        ScoredHotel(hotel=make_hotel(id=f"s{star}", star_rating=star), score=star / 10)
        for star in (1, 2, 3, 4, 5)
    ]
    out = lenses.stratified_best(scored, per_band=1)
    assert [s.hotel.id for s in out] == ["s5", "s4", "s3", "s2"]  # top 4 tiers, 1-star dropped


def test_stratified_best_no_band_no_star_returns_top_overall(
    make_hotel: Callable[..., Hotel],
) -> None:
    scored = [
        ScoredHotel(hotel=make_hotel(id="a"), score=0.3),
        ScoredHotel(hotel=make_hotel(id="b"), score=0.9),
    ]
    out = lenses.stratified_best(scored, per_band=1)
    assert [s.hotel.id for s in out] == ["b", "a"]  # top overall so the lens is never empty


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
