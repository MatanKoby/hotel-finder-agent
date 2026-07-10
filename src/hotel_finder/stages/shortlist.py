"""Cheap deterministic shortlist.

A fast pre-rank that trims the filtered candidate set to the top ~N before the expensive scoring
step runs. Uses only cheap signals (rating, review-count confidence, distance to the wanted area).
Deterministic, with a stable id tie-break.
"""

from __future__ import annotations

from hotel_finder.contracts import HotelQuery
from hotel_finder.models import Hotel
from hotel_finder.utils.geo import haversine
from hotel_finder.utils.text import normalize_text

_FAR_KM = 5.0  # distance at which the location penalty saturates


def _cheap_score(hotel: Hotel, query: HotelQuery) -> float:
    score = (hotel.rating or 0.0) / 5.0
    # A little confidence weight for well-reviewed places (saturates at 500 reviews).
    score += min((hotel.review_count or 0) / 500.0, 1.0) * 0.2

    if query.center is not None and hotel.location is not None:
        distance = haversine(hotel.location, query.center)
        score -= min(distance / _FAR_KM, 1.0) * 0.3

    if (
        query.desired_area
        and hotel.area
        and normalize_text(query.desired_area) in normalize_text(hotel.area)
    ):
        score += 0.2

    return score


def shortlist(hotels: list[Hotel], query: HotelQuery, size: int) -> list[Hotel]:
    """Return the top ``size`` candidates by cheap score (id tie-break for determinism)."""
    ranked = sorted(hotels, key=lambda h: (-_cheap_score(h, query), h.id))
    return ranked[:size]
