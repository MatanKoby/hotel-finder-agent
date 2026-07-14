"""The three lenses — pure projections over one scored candidate set.

These don't re-search or re-score; they select three different views of the same
``list[ScoredHotel]``. Overlap between lenses is data-dependent and expected.
"""

from __future__ import annotations

from collections import defaultdict

from hotel_finder.models import PriceBand
from hotel_finder.scoring.base import ScoredHotel

# The price-band fallback (star tiers) is capped to this many tiers so ``stratified_best`` never
# exceeds the lens's pick cap (``len(PriceBand)``); star ratings span 1-5, one more than the bands.
_MAX_TIERS = len(PriceBand)


def _top(scored: list[ScoredHotel], k: int) -> list[ScoredHotel]:
    """Top ``k`` by overall score, with a stable id tie-break."""
    return sorted(scored, key=lambda s: (-s.score, s.hotel.id))[:k]


def overall_standouts(scored: list[ScoredHotel], k: int) -> list[ScoredHotel]:
    """Top ``k`` overall, ignoring price tiers (may clump in one tier)."""
    return _top(scored, k)


def stratified_best(scored: list[ScoredHotel], per_band: int = 1) -> list[ScoredHotel]:
    """The best ``per_band`` from each price band, guaranteeing coverage across budgets.

    Bands are emitted in a fixed budget→luxury order; bands absent from the set are skipped. When
    **no** candidate carries a price band (e.g. a content-only search with no live rates), it falls
    back to stratifying by **star tier** so the lens still fills — see :func:`_stratified_by_star`.
    """
    by_band: dict[PriceBand, list[ScoredHotel]] = defaultdict(list)
    for item in scored:
        if item.hotel.price_band is not None:
            by_band[item.hotel.price_band].append(item)

    if not by_band:
        return _stratified_by_star(scored, per_band)

    picks: list[ScoredHotel] = []
    for band in PriceBand:  # deterministic budget -> luxury order
        picks.extend(_top(by_band.get(band, []), per_band))
    return picks


def _stratified_by_star(scored: list[ScoredHotel], per_tier: int) -> list[ScoredHotel]:
    """Fallback tiering when prices (and so bands) are absent: best ``per_tier`` per star class.

    Emits the highest star tiers first, capped to ``_MAX_TIERS`` so the pick count stays within the
    lens cap. When even star ratings are missing, returns the top overall so the lens isn't empty.
    """
    by_star: dict[int, list[ScoredHotel]] = defaultdict(list)
    for item in scored:
        if item.hotel.star_rating is not None:
            by_star[item.hotel.star_rating].append(item)

    if not by_star:
        return _top(scored, _MAX_TIERS)

    picks: list[ScoredHotel] = []
    for star in sorted(by_star, reverse=True)[:_MAX_TIERS]:  # 5-star first, deterministic
        picks.extend(_top(by_star[star], per_tier))
    return picks


def hidden_gems(scored: list[ScoredHotel], k: int, min_gem: float = 0.4) -> list[ScoredHotel]:
    """Top ``k`` by gem signal (over-performs its price, great rating, few reviews)."""
    gems = [s for s in scored if s.subscores.get("gem_signal", 0.0) >= min_gem]
    gems.sort(key=lambda s: (-s.subscores.get("gem_signal", 0.0), s.hotel.id))
    return gems[:k]
