"""Internal search context: what the stateless stages need, decoupled from the public request.

The pipeline resolves a :class:`~hotel_finder.contracts.HotelSearchRequest` (structured place, or
a geocoded ``text``) into this small value object, then hands it to shortlist and the scorers.
Keeping it separate from the public contract means those stages don't depend on the request shape,
and the resolved ``center`` (geocoding lands in M1c) flows in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hotel_finder.contracts import Filters
from hotel_finder.models import GeoPoint


@dataclass(frozen=True)
class SearchContext:
    """Resolved search parameters the shortlist and scorers read."""

    center: GeoPoint | None = None  # resolved coordinates for distance math
    desired_area: str | None = None  # neighborhood bias
    location_label: str | None = None  # human place name, for the LLM prompt
    filters: Filters = field(default_factory=Filters)  # price/amenity context for the LLM prompt
