"""Cross-provider merge + dedupe.

Per-source normalization already happened in each provider's adapter; this stage only reconciles
the *same* hotel arriving from *different* providers. Two records are the same hotel when their
names normalize equal and (if both have coordinates) they sit within a small radius of each other.
"""

from __future__ import annotations

from hotel_finder.models import Hotel
from hotel_finder.utils.geo import haversine
from hotel_finder.utils.text import normalize_text

_DUP_RADIUS_KM = 0.15  # 150 m — same name within this distance is treated as one hotel

# Optional scalar fields filled from the secondary record when the primary lacks them.
_COALESCE_FIELDS = (
    "location",
    "area",
    "address",
    "price_per_night",
    "currency",
    "price_band",
    "rating",
    "review_count",
    "star_rating",
    "url",
    "description",
)


def _same_hotel(a: Hotel, b: Hotel) -> bool:
    if normalize_text(a.name) != normalize_text(b.name):
        return False
    if a.location is not None and b.location is not None:
        return haversine(a.location, b.location) <= _DUP_RADIUS_KM
    return True  # same name, not enough coordinates to disprove


def _merge(primary: Hotel, other: Hotel) -> Hotel:
    """Merge ``other`` into ``primary``: keep primary's identity, fill its gaps, union the rest."""
    updates: dict[str, object] = {
        field: getattr(primary, field)
        if getattr(primary, field) is not None
        else getattr(other, field)
        for field in _COALESCE_FIELDS
    }
    updates["amenities"] = primary.amenities | other.amenities
    updates["sources"] = list(dict.fromkeys([*primary.sources, *other.sources]))
    return primary.model_copy(update=updates)


def dedupe(hotels: list[Hotel]) -> list[Hotel]:
    """Collapse duplicate hotels (same hotel from multiple providers) into single records."""
    merged: list[Hotel] = []
    for hotel in hotels:
        for i, existing in enumerate(merged):
            if _same_hotel(existing, hotel):
                merged[i] = _merge(existing, hotel)
                break
        else:
            merged.append(hotel)
    return merged
