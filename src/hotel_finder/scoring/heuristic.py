"""Deterministic heuristic scorer — the free default.

No network, no model: it derives value/location/character/gem_signal from the structured fields
already on each hotel, normalizing price within the provided shortlist. Fully reproducible, which
makes the whole pipeline unit-testable and evaluable at $0.
"""

from __future__ import annotations

from hotel_finder.context import SearchContext
from hotel_finder.models import Hotel
from hotel_finder.scoring.base import ScoredHotel, ScoreReport, overall_score
from hotel_finder.utils.geo import haversine
from hotel_finder.utils.text import normalize_text

_FAR_KM = 5.0  # distance at which the location score bottoms out
_REVIEW_SATURATION = 300.0  # review count at which "few reviews" scarcity reaches zero


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _value(hotel: Hotel, min_price: float, price_spread: float) -> float:
    rating_norm = (hotel.rating or 0.0) / 10.0
    if hotel.price_per_night is None or price_spread <= 0:
        affordability = 0.5
    else:
        price_norm = (hotel.price_per_night - min_price) / price_spread
        affordability = 1.0 - price_norm
    return _clamp(0.7 * rating_norm + 0.3 * affordability)


def _location(hotel: Hotel, context: SearchContext) -> float:
    if context.center is not None and hotel.location is not None:
        return _clamp(1.0 - haversine(hotel.location, context.center) / _FAR_KM)
    if context.desired_area and hotel.area:
        in_area = normalize_text(context.desired_area) in normalize_text(hotel.area)
        return 1.0 if in_area else 0.5
    return 0.6  # neutral when there's no location signal to go on


def _character(hotel: Hotel) -> float:
    amenity_richness = _clamp(len(hotel.amenities) / 8.0)
    star = (hotel.star_rating or 0) / 5.0
    has_description = 1.0 if hotel.description else 0.0
    return _clamp(0.5 * amenity_richness + 0.4 * star + 0.1 * has_description)


def _gem_signal(hotel: Hotel, value: float) -> float:
    rating_factor = _clamp(((hotel.rating or 0.0) - 8.0) / 2.0)  # 0 at 8.0, 1 at 10.0
    if hotel.review_count is None:
        scarcity = 0.5
    else:
        scarcity = _clamp(1.0 - hotel.review_count / _REVIEW_SATURATION)
    # Product: a gem must be highly rated AND under-the-radar AND a good value.
    return _clamp(rating_factor * scarcity * value)


def _rationale(hotel: Hotel, subscores: dict[str, float]) -> str:
    bits: list[str] = []
    if hotel.rating is not None:
        if hotel.price_per_night is not None:
            price = f"€{hotel.price_per_night:.0f}/night"
        else:
            price = "price n/a"
        bits.append(f"rated {hotel.rating}/10 at {price}")
    if hotel.area:
        bits.append(f"in {hotel.area}")
    if subscores["gem_signal"] >= 0.5:
        bits.append("over-performs its price with relatively few reviews — a likely hidden gem")
    elif subscores["value"] >= 0.7:
        bits.append("strong value for the quality")
    if not bits:
        return "Limited data available."
    return "; ".join(bits) + "."


class HeuristicScorer:
    """Scores hotels with a deterministic formula over their structured fields."""

    @property
    def report(self) -> ScoreReport:
        return ScoreReport(scorer="heuristic")

    async def score(self, hotels: list[Hotel], context: SearchContext) -> list[ScoredHotel]:
        prices = [h.price_per_night for h in hotels if h.price_per_night is not None]
        min_price = min(prices) if prices else 0.0
        price_spread = (max(prices) - min_price) if prices else 0.0

        scored: list[ScoredHotel] = []
        for hotel in hotels:
            value = _value(hotel, min_price, price_spread)
            location = _location(hotel, context)
            character = _character(hotel)
            gem = _gem_signal(hotel, value)
            subscores = {
                "value": round(value, 3),
                "location": round(location, 3),
                "character": round(character, 3),
                "gem_signal": round(gem, 3),
            }
            scored.append(
                ScoredHotel(
                    hotel=hotel,
                    score=round(overall_score(value, location, character), 3),
                    subscores=subscores,
                    rationale=_rationale(hotel, subscores),
                )
            )
        return scored
