"""Project scored hotels into the response ``Pick`` shape.

``Pick`` is **flat** (no nested ``hotel``): this stage promotes the fields the orchestrator renders
and reasons over up from the ``Hotel``, maps the internal ``subscores`` onto the wire field ``why``,
attaches the scorer's rationale and the hotel's priced ``offers`` (built by the pipeline per
``contract.md`` → Budget and offers), surfaces the provider photo (``image_url``) and coordinates so
the itinerary agent can plan around each hotel, and computes ``distance_to_desired_km`` (haversine
from the hotel to the resolved search ``center``; ``None`` when either the center or the hotel's
coordinates are missing).
"""

from __future__ import annotations

from hotel_finder.contracts import LensName, Pick, RateOffer
from hotel_finder.models import GeoPoint
from hotel_finder.scoring.base import ScoredHotel
from hotel_finder.utils.geo import haversine


def _lens_rationale(scored: ScoredHotel, lens: LensName | None) -> str:
    """The scorer's rationale, lightly tuned to the lens the pick is being shown under.

    The same hotel can appear in more than one lens; a short lens-specific clause explains *why it
    is in this projection* (its price tier for ``stratified_best``, the gem framing for
    ``hidden_gems``) without contradicting the scorer's own sentence.
    """
    base = scored.rationale
    if lens is LensName.STRATIFIED_BEST and scored.hotel.price_band is not None:
        note = f"best of the {scored.hotel.price_band.value} tier"
        return f"{base} ({note})" if base else f"{note.capitalize()}."
    if lens is LensName.HIDDEN_GEMS and "gem" not in base.lower():
        return f"Hidden gem: {base}" if base else "A likely hidden gem."
    return base


def to_pick(
    scored: ScoredHotel,
    offers: list[RateOffer],
    center: GeoPoint | None,
    lens: LensName | None = None,
) -> Pick:
    hotel = scored.hotel
    distance = (
        round(haversine(hotel.location, center), 2)
        if center is not None and hotel.location is not None
        else None
    )
    return Pick(
        name=hotel.name,
        score=scored.score,
        rationale=_lens_rationale(scored, lens),
        why=scored.subscores,
        area=hotel.area,
        distance_to_desired_km=distance,
        price_per_night=hotel.price_per_night,
        currency=hotel.currency,
        rating=hotel.rating,
        review_count=hotel.review_count,
        star_rating=hotel.star_rating,
        description=hotel.description,
        amenities=hotel.amenities,
        coordinates=hotel.location,
        image_url=hotel.image_url,
        url=hotel.url,
        offers=offers,
    )


def to_picks(
    scored: list[ScoredHotel],
    offers_by_id: dict[str, list[RateOffer]],
    center: GeoPoint | None,
    lens: LensName | None = None,
) -> list[Pick]:
    return [to_pick(item, offers_by_id.get(item.hotel.id, []), center, lens) for item in scored]
