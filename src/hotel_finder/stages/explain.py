"""Project scored hotels into the response ``Pick`` shape.

The rationale itself is produced by the scorer; this stage attaches it to a ``Pick`` and surfaces
the coordinates explicitly so the downstream itinerary agent can plan around each hotel.
"""

from __future__ import annotations

from hotel_finder.contracts import Pick
from hotel_finder.scoring.base import ScoredHotel


def to_pick(scored: ScoredHotel) -> Pick:
    return Pick(
        hotel=scored.hotel,
        score=scored.score,
        subscores=scored.subscores,
        rationale=scored.rationale,
        coordinates=scored.hotel.location,
    )


def to_picks(scored: list[ScoredHotel]) -> list[Pick]:
    return [to_pick(item) for item in scored]
