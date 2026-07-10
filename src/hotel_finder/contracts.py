"""The agent's request/response contract.

This is the stable surface the future orchestrator and the data-provider adapters hang off of,
so it's deliberately small and explicit. ``HotelQuery`` in, ``Recommendations`` out.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hotel_finder.models import Amenity, GeoPoint, Hotel


class Intent(StrEnum):
    """What kind of request this is. Modeled as a first-class field so intent-specific
    params can hang off it; today only ZONE is fully handled."""

    ZONE = "zone"  # "find me somewhere in this area" — broad search, then organize
    ANCHOR = "anchor"  # "I heard X is good" — peers of a named hotel (reserved for later)


class LensName(StrEnum):
    """The three projections over the single scored candidate set."""

    STRATIFIED_BEST = "stratified_best"
    OVERALL_STANDOUTS = "overall_standouts"
    HIDDEN_GEMS = "hidden_gems"


class HotelQuery(BaseModel):
    """A structured hotel-search request (free-text parsing is out of scope for v1)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    location: str  # city or area name, e.g. "Barcelona"
    intent: Intent = Intent.ZONE

    center: GeoPoint | None = None  # measure distance from here
    desired_area: str | None = None  # preferred neighborhood/district
    anchor_hotel: str | None = None  # for ANCHOR intent (reserved)

    check_in: date | None = None
    check_out: date | None = None
    guests: int | None = Field(default=None, ge=1)

    must_have_amenities: set[Amenity] = Field(default_factory=set)
    price_min: float | None = Field(default=None, ge=0.0)
    price_max: float | None = Field(default=None, ge=0.0)

    picks_per_lens: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def _validate_ranges(self) -> HotelQuery:
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min must be <= price_max")
        if (
            self.check_in is not None
            and self.check_out is not None
            and self.check_in >= self.check_out
        ):
            raise ValueError("check_in must be before check_out")
        return self


class Pick(BaseModel):
    """One recommended hotel within a lens, with its score and a human-readable rationale."""

    model_config = ConfigDict(extra="forbid")

    hotel: Hotel
    score: float
    subscores: dict[str, float] = Field(default_factory=dict)
    rationale: str = ""
    # Surfaced explicitly (mirrors hotel.location) so the itinerary agent can plan around it.
    coordinates: GeoPoint | None = None


class RecommendationMeta(BaseModel):
    """Diagnostics about how a recommendation was produced (for debugging/evaluation)."""

    model_config = ConfigDict(extra="forbid")

    providers_used: list[str] = Field(default_factory=list)
    candidates_found: int = 0
    candidates_after_filter: int = 0
    shortlisted: int = 0
    scorer: str = "heuristic"
    widened: bool = False


class Recommendations(BaseModel):
    """The agent's response: lens-projected picks over one scored candidate set."""

    model_config = ConfigDict(extra="forbid")

    query_id: str  # echoes HotelQuery.id
    lenses: dict[LensName, list[Pick]] = Field(default_factory=dict)
    meta: RecommendationMeta = Field(default_factory=RecommendationMeta)
