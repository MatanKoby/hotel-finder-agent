"""Project scored hotels into the response ``Pick`` shape.

``Pick`` is **flat** (no nested ``hotel``): this stage promotes the fields the orchestrator renders
and reasons over up from the ``Hotel``, maps the internal ``subscores`` onto the wire field ``why``,
attaches the scorer's rationale and the hotel's priced ``offers`` (built by the pipeline per
``contract.md`` → Budget and offers), and surfaces coordinates so the itinerary agent can plan
around each hotel. ``image_url`` and ``distance_to_desired_km`` are declared here but stay ``None``
until Batch C2 (provider-backed enrichment) populates them.
"""

from __future__ import annotations

from hotel_finder.contracts import Pick, RateOffer
from hotel_finder.scoring.base import ScoredHotel


def to_pick(scored: ScoredHotel, offers: list[RateOffer]) -> Pick:
    hotel = scored.hotel
    return Pick(
        name=hotel.name,
        score=scored.score,
        rationale=scored.rationale,
        why=scored.subscores,
        area=hotel.area,
        distance_to_desired_km=None,  # computed in Batch C2
        price_per_night=hotel.price_per_night,
        currency=hotel.currency,
        rating=hotel.rating,
        review_count=hotel.review_count,
        star_rating=hotel.star_rating,
        description=hotel.description,
        amenities=hotel.amenities,
        coordinates=hotel.location,
        image_url=None,  # populated from the provider in Batch C2
        url=hotel.url,
        offers=offers,
    )


def to_picks(
    scored: list[ScoredHotel], offers_by_id: dict[str, list[RateOffer]]
) -> list[Pick]:
    return [to_pick(item, offers_by_id.get(item.hotel.id, [])) for item in scored]
