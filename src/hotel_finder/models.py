"""Canonical domain types shared across the whole agent.

These are the types every data-provider adapter normalizes *into*, and every pipeline stage
operates *on*. Most fields are optional on purpose: a scraper may not expose a price band, a
small provider may lack coordinates. Keep this module free of pipeline or provider logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PriceBand(StrEnum):
    """Coarse price tier. Derived from price when a provider doesn't supply one."""

    BUDGET = "budget"
    MIDRANGE = "midrange"
    UPSCALE = "upscale"
    LUXURY = "luxury"


class Amenity(StrEnum):
    """Controlled amenity vocabulary. Adapters map raw provider strings onto these."""

    WIFI = "wifi"
    POOL = "pool"
    GYM = "gym"
    BREAKFAST = "breakfast"
    PARKING = "parking"
    AC = "ac"
    SPA = "spa"
    PET_FRIENDLY = "pet_friendly"
    KITCHEN = "kitchen"
    BAR = "bar"
    RESTAURANT = "restaurant"
    AIRPORT_SHUTTLE = "airport_shuttle"


# Synonyms seen in raw provider data, mapped onto the controlled vocabulary above.
_AMENITY_SYNONYMS: dict[str, Amenity] = {
    "wi-fi": Amenity.WIFI,
    "free wifi": Amenity.WIFI,
    "internet": Amenity.WIFI,
    "swimming pool": Amenity.POOL,
    "outdoor pool": Amenity.POOL,
    "indoor pool": Amenity.POOL,
    "fitness": Amenity.GYM,
    "fitness center": Amenity.GYM,
    "fitness centre": Amenity.GYM,
    "free breakfast": Amenity.BREAKFAST,
    "breakfast included": Amenity.BREAKFAST,
    "free parking": Amenity.PARKING,
    "garage": Amenity.PARKING,
    "air conditioning": Amenity.AC,
    "air-conditioning": Amenity.AC,
    "aircon": Amenity.AC,
    "wellness": Amenity.SPA,
    "sauna": Amenity.SPA,
    "pet friendly": Amenity.PET_FRIENDLY,
    "pet-friendly": Amenity.PET_FRIENDLY,
    "pets allowed": Amenity.PET_FRIENDLY,
    "kitchenette": Amenity.KITCHEN,
    "airport shuttle": Amenity.AIRPORT_SHUTTLE,
    "shuttle": Amenity.AIRPORT_SHUTTLE,
}


def normalize_amenity(raw: str) -> Amenity | None:
    """Map a raw amenity string onto the controlled vocabulary, or ``None`` if unknown."""
    key = raw.strip().lower()
    if not key:
        return None
    if key in _AMENITY_SYNONYMS:
        return _AMENITY_SYNONYMS[key]
    try:
        return Amenity(key)
    except ValueError:
        return None


def normalize_amenities(raws: Iterable[str]) -> set[Amenity]:
    """Normalize many raw amenity strings, dropping any that aren't in the vocabulary."""
    return {a for a in (normalize_amenity(r) for r in raws) if a is not None}


class GeoPoint(BaseModel):
    """A latitude/longitude pair. Immutable value object."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


class Hotel(BaseModel):
    """The canonical hotel record. Provider adapters produce these; stages consume them."""

    model_config = ConfigDict(extra="forbid")

    id: str  # provider-local id (globally unique together with ``source``)
    source: str  # name of the provider that produced this record
    name: str

    location: GeoPoint | None = None
    area: str | None = None  # neighborhood / district label
    address: str | None = None

    price_per_night: float | None = Field(default=None, ge=0.0)
    currency: str | None = None
    price_band: PriceBand | None = None

    rating: float | None = Field(default=None, ge=0.0, le=10.0)  # guest score, booking.com style
    review_count: int | None = Field(default=None, ge=0)
    star_rating: int | None = Field(default=None, ge=1, le=5)  # hotel class

    amenities: set[Amenity] = Field(default_factory=set)
    url: str | None = None
    description: str | None = None  # free text; the LLM scorer reads this for "character"

    raw: dict[str, Any] = Field(default_factory=dict)  # original provider payload
    sources: list[str] = Field(default_factory=list)  # provenance; grows on dedupe merge

    @model_validator(mode="after")
    def _ensure_provenance(self) -> Hotel:
        """Guarantee the originating ``source`` is always recorded in ``sources``."""
        if self.source and self.source not in self.sources:
            self.sources = [self.source, *self.sources]
        return self
