"""Internal search context: what the stateless stages need, decoupled from the public request.

The pipeline resolves a :class:`~hotel_finder.contracts.HotelSearchRequest` (structured place, or
a geocoded ``text``) into this small value object, then hands it to shortlist and the scorers.
Keeping it separate from the public contract means those stages don't depend on the request shape,
and the resolved ``center`` (geocoding lands in M1c) flows in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hotel_finder.contracts import Filters
from hotel_finder.models import Amenity, GeoPoint


@dataclass(frozen=True)
class PreferenceItem:
    """One wanted/unwanted signal, normalized from a ``HotelFeedback`` (its matched hotel's fresh
    fields, or the caller's echoed attributes). Feeds the refine preference bias and the LLM prompt
    (see ``pipeline.md`` → Refine, ``scoring.md`` → Preference bias)."""

    name: str = ""
    price_per_night: float | None = None
    area: str | None = None
    star_rating: int | None = None
    rating: float | None = None  # guest score, 0-10 (only from a matched hotel)
    location: GeoPoint | None = None  # only from a matched hotel
    amenities: frozenset[Amenity] = frozenset()
    property_type: str | None = None
    reason: str | None = None  # optional free text, for the LLM prompt


@dataclass(frozen=True)
class Preference:
    """The wanted/unwanted attribute signals driving a ``refine()`` call."""

    wanted: tuple[PreferenceItem, ...] = ()
    unwanted: tuple[PreferenceItem, ...] = ()

    def is_empty(self) -> bool:
        return not self.wanted and not self.unwanted


@dataclass(frozen=True)
class SearchContext:
    """Resolved search parameters the shortlist and scorers read."""

    center: GeoPoint | None = None  # resolved coordinates for distance math
    desired_area: str | None = None  # neighborhood bias
    location_label: str | None = None  # human place name, for the LLM prompt
    filters: Filters = field(default_factory=Filters)  # price/amenity context for the LLM prompt
    preference: Preference | None = None  # wanted/unwanted signals on a refine() call (LLM prompt)
