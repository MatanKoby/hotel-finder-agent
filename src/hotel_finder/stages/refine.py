"""Refinement (feedback loop): turn wanted/unwanted marks into what the pipeline applies.

``refine()`` (see ``pipeline.py``) re-runs discovery from the original trip, then this stage turns
the user's feedback into three pieces:

1. an **exclusion set** of already-seen ``Pick.id``s (wanted, unwanted, and the caller's ``exclude``
   list), so refine returns **new** options rather than the same list re-ranked;
2. a **wanted envelope** (:class:`RefineEnvelope`) — a multi-hotel analogue of the anchor envelope
   that tightens the filters toward the liked hotels (price window + star/rating floors) and
   re-centres ranking on their centroid; and
3. a **preference bias** (:func:`apply_preference`) — a bounded post-scoring nudge toward the wanted
   attribute profile and away from the unwanted one, applied to whatever scorer ran.

The agent is stateless: every piece is rebuilt from the request each call, nothing is remembered.
Degenerate feedback (nothing resolvable) yields empty pieces, so refine degrades to a plain
re-search rather than crashing (see ``contract.md`` → Error philosophy). Design: ``pipeline.md`` →
Refine, ``scoring.md`` → Preference bias, knobs in ``config.md`` → Refine knobs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hotel_finder.config import Settings
from hotel_finder.context import Preference, PreferenceItem
from hotel_finder.contracts import HotelFeedback, HotelRefineRequest
from hotel_finder.models import GeoPoint, Hotel, PriceBand
from hotel_finder.scoring.base import ScoredHotel
from hotel_finder.stages.anchor import find_anchor
from hotel_finder.stages.filtering import FilterCriteria
from hotel_finder.utils.text import normalize_text


def pick_id(hotel: Hotel) -> str:
    """The stable ``Pick.id`` for a hotel (``"{source}:{id}"``); the search->refine identity."""
    return f"{hotel.source}:{hotel.id}"


def match_feedback(candidates: list[Hotel], feedback: HotelFeedback) -> Hotel | None:
    """Locate the candidate a feedback item refers to: by ``Pick.id`` first, then normalized name.

    ``id`` is the preferred, exact identity (the orchestrator echoes back what it was given). Absent
    or unmatched, a non-empty ``name`` falls back to the same matcher as ``intent=anchor``
    (``find_anchor``: exact, else a unique containment). No id and no name resolves to ``None``.
    """
    if feedback.id:
        for hotel in candidates:
            if pick_id(hotel) == feedback.id:
                return hotel
    if feedback.name.strip():
        return find_anchor(candidates, feedback.name)
    return None


def _item(feedback: HotelFeedback, matched: Hotel | None) -> PreferenceItem:
    """A normalized signal from a feedback item: prefer the matched (fresh) hotel, else its echoed
    ``attributes``, else just the name/reason (still useful context for the LLM)."""
    if matched is not None:
        return PreferenceItem(
            name=matched.name,
            price_per_night=matched.price_per_night,
            area=matched.area,
            star_rating=matched.star_rating,
            rating=matched.rating,
            location=matched.location,
            amenities=frozenset(matched.amenities),
            property_type=None,  # Hotel carries no property_type today
            reason=feedback.reason,
        )
    attrs = feedback.attributes
    if attrs is not None:
        return PreferenceItem(
            name=feedback.name,
            price_per_night=attrs.price_per_night,
            area=attrs.area,
            star_rating=attrs.star_rating,
            amenities=frozenset(attrs.amenities),
            property_type=attrs.property_type,
            reason=feedback.reason,
        )
    return PreferenceItem(name=feedback.name, reason=feedback.reason)


def _resolve_group(
    candidates: list[Hotel], feedback: list[HotelFeedback]
) -> tuple[list[PreferenceItem], set[str]]:
    """Resolve a wanted/unwanted group to preference items + the ``Pick.id``s to exclude."""
    items: list[PreferenceItem] = []
    exclude: set[str] = set()
    for entry in feedback:
        matched = match_feedback(candidates, entry)
        if matched is not None:
            exclude.add(pick_id(matched))
        if entry.id:
            exclude.add(entry.id)  # exclude the echoed id even if it matched nothing this round
        items.append(_item(entry, matched))
    return items, exclude


# --- wanted envelope (tighten filters + re-centre; parallels stages/anchor.py) ---------------


def _max_opt(a: float | None, b: float | None) -> float | None:
    """The tighter (larger) of two optional lower bounds; ignores ``None``."""
    values = [v for v in (a, b) if v is not None]
    return max(values) if values else None


def _min_opt(a: float | None, b: float | None) -> float | None:
    """The tighter (smaller) of two optional upper bounds; ignores ``None``."""
    values = [v for v in (a, b) if v is not None]
    return min(values) if values else None


def _int_max_opt(a: int | None, b: int | None) -> int | None:
    values = [v for v in (a, b) if v is not None]
    return max(values) if values else None


def _centroid(points: list[GeoPoint]) -> GeoPoint:
    return GeoPoint(
        lat=sum(p.lat for p in points) / len(points),
        lon=sum(p.lon for p in points) / len(points),
    )


@dataclass(frozen=True)
class RefineEnvelope:
    """Price/area/rating envelope from the wanted hotels that new options should sit within.

    Every field is optional (the wanted set may lack prices, stars, or coordinates).
    :meth:`is_empty` reports when nothing usable was derived, in which case the refine is
    indistinguishable from a plain re-search.
    """

    center: GeoPoint | None = None
    radius_km: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    min_star: int | None = None
    min_guest_rating: float | None = None

    def is_empty(self) -> bool:
        return (
            self.center is None
            and self.price_min is None
            and self.price_max is None
            and self.min_star is None
            and self.min_guest_rating is None
        )

    def to_criteria(self, base: FilterCriteria) -> FilterCriteria:
        """Fold this envelope into the request's own hard filters (``base``), only ever tightening.

        The stricter of each price/star/rating bound wins; must-have amenities pass through
        unchanged (shared wanted amenities are a *soft* bias, see :func:`apply_preference`); and the
        wanted centroid replaces the request centre so new options cluster around the liked hotels.
        """
        anchored = self.center is not None
        return FilterCriteria(
            must_have_amenities=base.must_have_amenities,
            price_min=_max_opt(base.price_min, self.price_min),
            price_max=_min_opt(base.price_max, self.price_max),
            min_star=_int_max_opt(base.min_star, self.min_star),
            min_guest_rating=_max_opt(base.min_guest_rating, self.min_guest_rating),
            center=self.center if anchored else base.center,
            radius_km=self.radius_km if anchored else base.radius_km,
        )


def refine_envelope(wanted: list[PreferenceItem], settings: Settings) -> RefineEnvelope:
    """Derive the wanted envelope from the liked hotels' shared price/class/location signals.

    A price window spanning their prices (the ``refine_price_*_factor`` knobs times the min/max),
    star and guest-rating floors near the group minimum (less the tolerances), and a re-centre on
    the centroid of those with coordinates. A dimension no wanted hotel carries is dropped.
    """
    prices = [i.price_per_night for i in wanted if i.price_per_night is not None]
    stars = [i.star_rating for i in wanted if i.star_rating is not None]
    ratings = [i.rating for i in wanted if i.rating is not None]
    locations = [i.location for i in wanted if i.location is not None]

    price_min = round(min(prices) * settings.refine_price_low_factor, 2) if prices else None
    price_max = round(max(prices) * settings.refine_price_high_factor, 2) if prices else None
    min_star = max(1, min(stars) - settings.refine_star_tolerance) if stars else None
    min_rating = max(0.0, min(ratings) - settings.refine_rating_tolerance) if ratings else None
    center = _centroid(locations) if locations else None

    return RefineEnvelope(
        center=center,
        radius_km=settings.refine_radius_km if center is not None else None,
        price_min=price_min,
        price_max=price_max,
        min_star=min_star,
        min_guest_rating=min_rating,
    )


# --- preference bias (soft, post-scoring; parallels neither anchor nor the scorers) ----------


@dataclass(frozen=True)
class _Profile:
    """The aggregate attribute footprint of a wanted or unwanted group."""

    areas: frozenset[str]
    bands: frozenset[PriceBand]
    stars: frozenset[int]
    amenities: frozenset[str]
    property_types: frozenset[str]

    def is_empty(self) -> bool:
        return not (self.areas or self.bands or self.stars or self.amenities or self.property_types)


def _band_of(price: float | None, settings: Settings) -> PriceBand | None:
    return settings.price_band_for(price) if price is not None else None


def _profile(items: Iterable[PreferenceItem], settings: Settings) -> _Profile:
    areas: set[str] = set()
    bands: set[PriceBand] = set()
    stars: set[int] = set()
    amenities: set[str] = set()
    property_types: set[str] = set()
    for item in items:
        if item.area and (area := normalize_text(item.area)):
            areas.add(area)
        if (band := _band_of(item.price_per_night, settings)) is not None:
            bands.add(band)
        if item.star_rating is not None:
            stars.add(item.star_rating)
        amenities.update(a.value for a in item.amenities)
        if item.property_type and (ptype := normalize_text(item.property_type)):
            property_types.add(ptype)
    return _Profile(
        frozenset(areas), frozenset(bands), frozenset(stars),
        frozenset(amenities), frozenset(property_types),
    )


def _similarity(hotel: Hotel, profile: _Profile, settings: Settings) -> float:
    """Fraction of the profile's dimensions the hotel matches, in ``[0, 1]`` (0 if none apply)."""
    dims: list[float] = []
    if profile.areas:
        hotel_area = normalize_text(hotel.area) if hotel.area else ""
        dims.append(1.0 if hotel_area and hotel_area in profile.areas else 0.0)
    band = hotel.price_band or _band_of(hotel.price_per_night, settings)
    if profile.bands and band is not None:
        dims.append(1.0 if band in profile.bands else 0.0)
    if profile.stars and hotel.star_rating is not None:
        dims.append(1.0 if hotel.star_rating in profile.stars else 0.0)
    if profile.amenities:
        hotel_amenities = {a.value for a in hotel.amenities}
        dims.append(len(hotel_amenities & profile.amenities) / len(profile.amenities))
    return sum(dims) / len(dims) if dims else 0.0


def apply_preference(
    scored: list[ScoredHotel], preference: Preference, settings: Settings
) -> list[ScoredHotel]:
    """Nudge each overall score toward the wanted profile and away from the unwanted one.

    The bounded delta ``refine_bias_weight * (sim_wanted - sim_unwanted)`` is added to the overall
    score and re-clamped to ``[0, 1]``, and recorded as ``why["preference"]``. Applied on top of
    **whatever scorer ran**, so the bias is deterministic even on the heuristic path. A no-op when
    there is no usable preference.
    """
    wanted = _profile(preference.wanted, settings)
    unwanted = _profile(preference.unwanted, settings)
    if wanted.is_empty() and unwanted.is_empty():
        return scored

    weight = settings.refine_bias_weight
    out: list[ScoredHotel] = []
    for item in scored:
        sim_w = _similarity(item.hotel, wanted, settings) if not wanted.is_empty() else 0.0
        sim_u = _similarity(item.hotel, unwanted, settings) if not unwanted.is_empty() else 0.0
        delta = weight * (sim_w - sim_u)
        new_score = max(0.0, min(1.0, item.score + delta))
        subscores = {**item.subscores, "preference": round(delta, 3)}
        out.append(item.model_copy(update={"score": round(new_score, 3), "subscores": subscores}))
    return out


# --- the plan the pipeline consumes ----------------------------------------------------------


@dataclass(frozen=True)
class RefinePlan:
    """Everything ``refine()`` derives from the feedback before running the filter/score path."""

    exclude_ids: frozenset[str]
    envelope: RefineEnvelope
    preference: Preference


def plan_refine(
    candidates: list[Hotel], request: HotelRefineRequest, settings: Settings
) -> RefinePlan:
    """Resolve the request's feedback against the re-discovered candidates into a plan.

    Exclusion = the caller's ``exclude`` ids ∪ the resolved wanted/unwanted ids. The envelope comes
    from the wanted items; the preference carries both groups (for the soft bias and the LLM
    prompt).
    """
    wanted_items, wanted_exclude = _resolve_group(candidates, request.wanted)
    unwanted_items, unwanted_exclude = _resolve_group(candidates, request.unwanted)

    exclude_ids = set(request.exclude) | wanted_exclude | unwanted_exclude
    return RefinePlan(
        exclude_ids=frozenset(exclude_ids),
        envelope=refine_envelope(wanted_items, settings),
        preference=Preference(wanted=tuple(wanted_items), unwanted=tuple(unwanted_items)),
    )
