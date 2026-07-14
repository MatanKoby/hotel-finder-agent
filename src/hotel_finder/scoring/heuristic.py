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
_FEW_REVIEWS = 150  # at/below this a "relatively few reviews" claim in the rationale is truthful


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
        return _area_affinity(context.desired_area, hotel.area)
    return 0.6  # neutral when there's no location signal to go on


def _significant_tokens(text: str) -> set[str]:
    """Words worth matching on: drop short articles ("el", "la", "de") that many areas share."""
    return {token for token in text.split() if len(token) > 2}


def _area_affinity(desired_area: str, area: str) -> float:
    """Graded name-only neighbourhood fit, used when there's no ``center`` for real distance.

    A flat match/non-match is too coarse (the finding: "El Born"/"Gràcia" barely move the ranking).
    Instead: an exact/substring match scores top, a partial word overlap earns partial credit, and a
    known-different neighbourhood floors clearly below both (and below the no-signal neutral) so the
    wanted area actually rises to the top.
    """
    desired = normalize_text(desired_area)
    hotel_area = normalize_text(area)
    if desired and (desired in hotel_area or hotel_area in desired):
        return 1.0
    desired_tokens = _significant_tokens(desired)
    shared = desired_tokens & _significant_tokens(hotel_area)
    if desired_tokens and shared:
        return _clamp(0.55 + 0.35 * len(shared) / len(desired_tokens))
    return 0.35


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
        # Only claim "few reviews" when that's actually true; otherwise the rationale contradicts
        # a hotel with many (or unknown) reviews (see roadmap P1/P6 finding 5).
        if hotel.review_count is not None and hotel.review_count <= _FEW_REVIEWS:
            bits.append(
                f"a likely hidden gem: strong rating on only {hotel.review_count} reviews"
            )
        else:
            bits.append("a likely hidden gem: over-performs its price for the quality")
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
