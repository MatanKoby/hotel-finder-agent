"""Project scored hotels into the response ``Pick`` shape.

The rationale itself is produced by the scorer; this stage attaches it to a ``Pick``, surfaces the
coordinates explicitly (so the downstream itinerary agent can plan around each hotel), and attaches
the hotel's priced ``offers`` (built by the pipeline per ``contract.md`` → Budget and offers).
"""

from __future__ import annotations

from hotel_finder.contracts import Pick, RateOffer
from hotel_finder.scoring.base import ScoredHotel


def to_pick(scored: ScoredHotel, offers: list[RateOffer]) -> Pick:
    return Pick(
        hotel=scored.hotel,
        score=scored.score,
        subscores=scored.subscores,
        rationale=scored.rationale,
        coordinates=scored.hotel.location,
        offers=offers,
    )


def to_picks(
    scored: list[ScoredHotel], offers_by_id: dict[str, list[RateOffer]]
) -> list[Pick]:
    return [to_pick(item, offers_by_id.get(item.hotel.id, [])) for item in scored]
