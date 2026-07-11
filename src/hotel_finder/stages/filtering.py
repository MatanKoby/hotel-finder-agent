"""Hard, deterministic filter.

Drops any candidate that fails a must-have constraint: required amenities, price range, and
(when a center + radius are given) area. The pipeline's bounded-agency widening relaxes the
``FilterCriteria`` it passes here and re-filters — this stage itself has no notion of retries.
"""

from __future__ import annotations

from dataclasses import dataclass

from hotel_finder.models import Amenity, GeoPoint, Hotel
from hotel_finder.utils.geo import haversine


@dataclass(frozen=True)
class FilterCriteria:
    """The hard constraints a candidate must satisfy. Absent constraints are no-ops."""

    must_have_amenities: frozenset[Amenity] = frozenset()
    price_min: float | None = None
    price_max: float | None = None
    min_star: int | None = None
    min_guest_rating: float | None = None  # guest score, 0-10
    center: GeoPoint | None = None
    radius_km: float | None = None  # area bound around ``center``; None = unbounded


def passes(hotel: Hotel, criteria: FilterCriteria) -> bool:
    """Whether a single hotel satisfies every hard constraint."""
    if not criteria.must_have_amenities <= hotel.amenities:
        return False

    # Price bounds: a hotel with an unknown price can't be confirmed to fit, so exclude it.
    if criteria.price_min is not None and (
        hotel.price_per_night is None or hotel.price_per_night < criteria.price_min
    ):
        return False
    if criteria.price_max is not None and (
        hotel.price_per_night is None or hotel.price_per_night > criteria.price_max
    ):
        return False

    # Quality bounds: unknown star / rating can't be confirmed to fit, so exclude when a bound set.
    if criteria.min_star is not None and (
        hotel.star_rating is None or hotel.star_rating < criteria.min_star
    ):
        return False
    if criteria.min_guest_rating is not None and (
        hotel.rating is None or hotel.rating < criteria.min_guest_rating
    ):
        return False

    # Area bound: must sit within radius_km of center (and therefore have coordinates).
    return not (
        criteria.center is not None
        and criteria.radius_km is not None
        and (
            hotel.location is None
            or haversine(hotel.location, criteria.center) > criteria.radius_km
        )
    )


def hard_filter(hotels: list[Hotel], criteria: FilterCriteria) -> list[Hotel]:
    """Keep only the hotels that satisfy ``criteria``."""
    return [hotel for hotel in hotels if passes(hotel, criteria)]
