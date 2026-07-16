"""The submodule's request/response contract (`contracts.py`).

The stable typed surface this repo exposes **as a git submodule** to an orchestrator agent:
``HotelSearchRequest`` in, ``HotelSearchResponse`` out, via the ``search`` entry point in
``pipeline.py``. Built on the domain types in ``models.py``.

The Pydantic v2 models are both the contract **and** the shared validator: the orchestrator
imports ``HotelSearchRequest`` and constructs it on its own side, so a malformed request raises
``pydantic.ValidationError`` at construction, before ``search()`` is ever entered. During work the
agent never raises for a data outcome; problems become ``warnings`` + ``status`` on the response.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hotel_finder.models import Amenity, GeoPoint


class Intent(StrEnum):
    """What kind of request this is. Both ZONE and ANCHOR are handled (see ``pipeline.md``)."""

    ZONE = "zone"  # "find me somewhere in this area" — broad search, then organize
    ANCHOR = "anchor"  # "I heard X is good" — peers of a named hotel (needs ``anchor_hotel``)


class LensName(StrEnum):
    """The three projections over the single scored candidate set."""

    STRATIFIED_BEST = "stratified_best"
    OVERALL_STANDOUTS = "overall_standouts"
    HIDDEN_GEMS = "hidden_gems"


# --- request ---------------------------------------------------------------------------------


class Occupancy(BaseModel):
    """Guests for one room."""

    model_config = ConfigDict(extra="forbid")

    adults: int = Field(default=2, ge=1)
    children_ages: list[int] = Field(default_factory=list)


class Place(BaseModel):
    """Where to search. Accepts structured fields **and** free text; structured wins when present,
    ``text`` is the fallback the pipeline geocodes (see ``data-sources.md``). At least one usable
    path (``city``, ``center``, or ``text``) is required."""

    model_config = ConfigDict(extra="forbid")

    country_code: str | None = None  # ISO-3166-1 alpha-2, e.g. "ES"
    city: str | None = None
    center: GeoPoint | None = None  # precise "near this point"
    radius_km: float | None = Field(default=5.0, ge=0.0)  # only meaningful with center
    text: str | None = None  # free-text place name, geocoded when structured fields are absent
    desired_area: str | None = None  # neighborhood bias for ranking, not a hard filter

    @model_validator(mode="after")
    def _at_least_one_path(self) -> Place:
        if self.center is None and not self.city and not self.text:
            raise ValueError("Place requires one of: city (with country_code), center, or text")
        return self


class Stay(BaseModel):
    """Dates + occupancy, needed for real prices. Omit for content-only (no live rates)."""

    model_config = ConfigDict(extra="forbid")

    check_in: date
    check_out: date
    currency: str = "EUR"
    rooms: list[Occupancy] | None = None
    """Per-room occupancy override. ``None`` derives a single room from ``request.guests``; a set
    value **overrides** ``guests`` (multi-room bookings). ``guest_nationality`` is **not** here: it
    is trip-level (``request.guest_nationality``), a traveler attribute shared with siblings."""

    @model_validator(mode="after")
    def _validate_dates(self) -> Stay:
        if self.check_in >= self.check_out:
            raise ValueError("check_in must be before check_out")
        return self


class Filters(BaseModel):
    """Hard and soft constraints the pipeline applies. Absent fields are no-ops."""

    model_config = ConfigDict(extra="forbid")

    price_min: float | None = Field(default=None, ge=0.0)  # per-night
    price_max: float | None = Field(default=None, ge=0.0)  # per-night
    min_star: int | None = Field(default=None, ge=1, le=5)  # hotel class
    min_guest_rating: float | None = Field(default=None, ge=0.0, le=10.0)  # guest score 0-10
    refundable: bool | None = None  # None returns both kinds; True/False restricts
    must_have_amenities: set[Amenity] = Field(default_factory=set)
    property_types: set[str] = Field(default_factory=set)  # empty = all lodging types

    @model_validator(mode="after")
    def _validate_price_range(self) -> Filters:
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min must be <= price_max")
        return self


class HotelSearchRequest(BaseModel):
    """A structured hotel-search request. ``extra="forbid"`` fails fast on an orchestrator typo
    (safe because the submodule is commit-pinned)."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    place: Place
    stay: Stay | None = None
    guests: Occupancy = Field(default_factory=Occupancy)  # trip-level occupancy
    guest_nationality: str = "US"  # trip-level traveler attribute; affects rates upstream
    filters: Filters = Field(default_factory=Filters)
    lenses: list[LensName] | None = None  # None means all three
    picks_per_lens: int = Field(default=3, ge=1)
    # intent / anchor_hotel are a pair. Default ZONE leaves anchor_hotel inert (the common path), so
    # the wire shape is stable whether or not the orchestrator sets them. intent=ANCHOR means "find
    # peers of anchor_hotel" (see pipeline.md → Anchor intent) and requires a non-empty name.
    intent: Intent = Intent.ZONE
    anchor_hotel: str | None = None  # the named hotel whose peers to find, when intent=ANCHOR

    @model_validator(mode="after")
    def _validate_anchor(self) -> HotelSearchRequest:
        if self.intent is Intent.ANCHOR and not (self.anchor_hotel and self.anchor_hotel.strip()):
            raise ValueError("intent=anchor requires a non-empty anchor_hotel")
        return self


# --- refinement (feedback loop) --------------------------------------------------------------


class HotelFeedbackAttributes(BaseModel):
    """Optional echo of a prior ``Pick``'s fields, used to bias the refine result when the hotel is
    no longer in the freshly discovered candidate set. Forgiving (``extra="ignore"``) so a caller
    can send more without being rejected."""

    model_config = ConfigDict(extra="ignore")

    price_per_night: float | None = Field(default=None, ge=0.0)
    area: str | None = None
    star_rating: int | None = Field(default=None, ge=1, le=5)
    amenities: set[Amenity] = Field(default_factory=set)
    property_type: str | None = None


class HotelFeedback(BaseModel):
    """One wanted/unwanted signal: a reduced echo of a prior ``Pick`` (see ``contract.md`` →
    Refinement). Forgiving (``extra="ignore"``) so it is easy for the caller to build."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None  # a prior Pick.id, the preferred identity; None falls back to name
    name: str = ""  # identity fallback, and a useful signal for the LLM scorer
    attributes: HotelFeedbackAttributes | None = None
    reason: str | None = None  # optional free text, passed to the LLM scorer as context


class HotelRefineRequest(BaseModel):
    """A refinement (feedback-loop) request: the original trip ``base`` plus the user's wanted /
    unwanted marks on a prior response. ``refine()`` returns the same ``HotelSearchResponse`` as
    ``search`` (see ``contract.md`` → Refinement). ``extra="forbid"`` fails fast on a typo."""

    model_config = ConfigDict(extra="forbid")

    base: HotelSearchRequest  # the original trip context; validated as its own model
    wanted: list[HotelFeedback] = Field(default_factory=list)  # bias toward; surface new like these
    unwanted: list[HotelFeedback] = Field(default_factory=list)  # excluded + biased against
    exclude: list[str] = Field(default_factory=list)  # Pick.ids already shown; not repeated
    round: int = Field(default=1, ge=1)  # refinement round, echoed into diagnostics.round


# --- response --------------------------------------------------------------------------------


class RateOffer(BaseModel):
    """Read-only price information for one rate. No booking token in M1 (booking deferred)."""

    model_config = ConfigDict(extra="forbid")

    total: float = Field(ge=0.0)  # stay total
    currency: str
    per_night: float | None = Field(default=None, ge=0.0)
    board: str | None = None  # e.g. "Room Only", "Breakfast Included"
    refundable: bool
    over_budget: bool = False  # only True in the budget-too-low fallback (see pipeline)


class ResolvedQuery(BaseModel):
    """What was **actually** searched, so the orchestrator can reason about the result."""

    model_config = ConfigDict(extra="forbid")

    center: GeoPoint | None = None
    city: str | None = None
    area: str | None = None  # neighborhood the search biased toward (echoes place.desired_area)
    check_in: date | None = None
    check_out: date | None = None
    currency: str | None = None


class Pick(BaseModel):
    """One recommended hotel within a lens: **flat**, rendering-ready.

    No nested ``hotel`` — the fields the orchestrator renders and reasons over are promoted to the
    top level; internal-only fields (``raw``, full ``sources``) stay off the wire. ``score`` is the
    single overall score (``0..1``), the **same** value in every lens (lenses differ in selection,
    not scale), so ``stratified_best`` must not re-normalize within a price tier.
    """

    model_config = ConfigDict(extra="forbid")

    id: str  # stable "{source}:{provider_id}"; the search->refine identity (see contract.md)
    name: str
    score: float = Field(ge=0.0, le=1.0)  # overall, normalized, comparable across lenses
    rationale: str = ""
    why: dict[str, float] = Field(default_factory=dict)  # structured subscores; scorer-dependent
    area: str | None = None
    distance_to_desired_km: float | None = None  # None when no desired_area / center was given
    price_per_night: float | None = None
    currency: str | None = None
    rating: float | None = None  # guest score, 0-10
    review_count: int | None = None
    star_rating: int | None = None  # hotel class, 1-5
    description: str | None = None  # the "character" blurb
    amenities: set[Amenity] = Field(default_factory=set)
    coordinates: GeoPoint | None = None  # so the itinerary agent can plan around each hotel
    image_url: str | None = None  # provider-supplied photo; None for providers/hotels without one
    url: str | None = None
    offers: list[RateOffer] = Field(default_factory=list)


class Diagnostics(BaseModel):
    """Diagnostics about how a recommendation was produced (for debugging/evaluation)."""

    model_config = ConfigDict(extra="forbid")

    providers_used: list[str] = Field(default_factory=list)
    candidates_found: int = 0
    candidates_after_filter: int = 0
    shortlisted: int = 0
    scorer: str = "heuristic"  # the scorer that actually ran (see scoring.md)
    widened: bool = False
    refined: bool = False  # True on a refine() response
    round: int = 1  # echoes HotelRefineRequest.round on a refine() response


class HotelSearchResponse(BaseModel):
    """A result envelope: partial results and problems are data to read, not exceptions to catch."""

    model_config = ConfigDict(extra="forbid")

    request_id: str  # echoes the request
    # data outcome; the orchestrator owns the outer transport status (see contract.md)
    agent_status: Literal["ok", "empty", "degraded"] = "ok"
    warnings: list[str] = Field(default_factory=list)
    resolved: ResolvedQuery = Field(default_factory=ResolvedQuery)
    lenses: dict[LensName, list[Pick]] = Field(default_factory=dict)
    diagnostics: Diagnostics = Field(default_factory=Diagnostics)
