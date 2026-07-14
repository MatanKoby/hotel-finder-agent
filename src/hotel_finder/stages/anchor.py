"""ANCHOR intent: find peers of a named hotel.

The orchestrator sometimes asks "I heard *Hotel X* is good — find me places like it" rather than
"find me somewhere in this area". That is ``intent=anchor`` with an ``anchor_hotel`` name (see
``contract.md``). Because a request always carries a ``place`` (the anchor's city/area), the
pipeline discovers the usual candidate set first, then this stage:

1. **locates** the named anchor among those candidates (:func:`find_anchor`), and
2. derives a **peer envelope** from it (:func:`anchor_envelope`) — proximity to the anchor, a price
   window around its price, and star/guest-rating floors near its class.

The envelope is expressed as :class:`~hotel_finder.stages.filtering.FilterCriteria`, so the normal
hard-filter + bounded-agency widening + scoring machinery does the rest; the pipeline excludes the
anchor itself (it is the reference, not a recommendation) and ranks peers by proximity to it. If the
anchor can't be found, or carries too little data to constrain peers, the pipeline warns and falls
back to a broad zone search (never crashes; see ``pipeline.md`` → Anchor intent).
"""

from __future__ import annotations

from dataclasses import dataclass

from hotel_finder.config import Settings
from hotel_finder.models import GeoPoint, Hotel
from hotel_finder.stages.filtering import FilterCriteria
from hotel_finder.utils.text import normalize_text


def find_anchor(candidates: list[Hotel], anchor_name: str) -> Hotel | None:
    """Match the named anchor against the candidate set by normalized name.

    An exact normalized-name match wins (first-seen on a tie; the set is already deduped). Otherwise
    a **unique** containment match (either direction) is accepted, so "Hotel Arts" finds "Hotel Arts
    Barcelona" and vice versa. An ambiguous containment (several hotels match) or no match returns
    ``None`` — the caller then falls back to a broad zone search rather than guess wrong.
    """
    target = normalize_text(anchor_name)
    if not target:
        return None
    exact = [h for h in candidates if normalize_text(h.name) == target]
    if exact:
        return exact[0]
    contained = [
        h
        for h in candidates
        if (name := normalize_text(h.name)) and (target in name or name in target)
    ]
    return contained[0] if len(contained) == 1 else None


def _max_opt(a: float | None, b: float | None) -> float | None:
    """The tighter (larger) of two optional lower bounds; ignores ``None``."""
    values = [v for v in (a, b) if v is not None]
    return max(values) if values else None


def _min_opt(a: float | None, b: float | None) -> float | None:
    """The tighter (smaller) of two optional upper bounds; ignores ``None``."""
    values = [v for v in (a, b) if v is not None]
    return min(values) if values else None


@dataclass(frozen=True)
class AnchorEnvelope:
    """The band/area/rating envelope derived from an anchor hotel that its peers must sit within.

    Every field is optional: an anchor missing coordinates yields no ``center``, one missing a price
    yields no price window, and so on. :meth:`is_empty` reports when nothing usable was derived (the
    peer search would then be indistinguishable from a zone search).
    """

    center: GeoPoint | None = None
    radius_km: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    min_star: int | None = None
    min_guest_rating: float | None = None

    def is_empty(self) -> bool:
        """True when the anchor gave no usable constraint (no geo, price, star, or rating)."""
        return (
            self.center is None
            and self.price_min is None
            and self.price_max is None
            and self.min_star is None
            and self.min_guest_rating is None
        )

    def to_criteria(self, base: FilterCriteria) -> FilterCriteria:
        """Fold this envelope into the request's own hard filters (``base``).

        The request's constraints still apply — the peer envelope only ever **tightens** them: the
        stricter of each price/star/rating bound wins, and the anchor's location replaces the
        request centre for peer proximity (peers cluster around the anchor, not the search point).
        Must-have amenities are the request's and pass through unchanged.
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


def _int_max_opt(a: int | None, b: int | None) -> int | None:
    values = [v for v in (a, b) if v is not None]
    return max(values) if values else None


def anchor_envelope(anchor: Hotel, settings: Settings) -> AnchorEnvelope:
    """Derive the peer envelope from an anchor hotel using the ``anchor_*`` settings.

    * proximity — the anchor's coordinates + ``anchor_radius_km`` (skipped if it has no location);
    * price window — ``[price * anchor_price_low_factor, price * anchor_price_high_factor]`` around
      the anchor's per-night price (skipped if it has no price);
    * class floors — ``star - anchor_star_tolerance`` and ``rating - anchor_rating_tolerance``, so
      peers are of comparable-or-better class without pinning an exact star (skipped when absent).
    """
    center = anchor.location
    radius_km = settings.anchor_radius_km if center is not None else None

    price_min = price_max = None
    if anchor.price_per_night is not None:
        price_min = round(anchor.price_per_night * settings.anchor_price_low_factor, 2)
        price_max = round(anchor.price_per_night * settings.anchor_price_high_factor, 2)

    min_star = None
    if anchor.star_rating is not None:
        min_star = max(1, anchor.star_rating - settings.anchor_star_tolerance)

    min_guest_rating = None
    if anchor.rating is not None:
        min_guest_rating = max(0.0, anchor.rating - settings.anchor_rating_tolerance)

    return AnchorEnvelope(
        center=center,
        radius_km=radius_km,
        price_min=price_min,
        price_max=price_max,
        min_star=min_star,
        min_guest_rating=min_guest_rating,
    )
