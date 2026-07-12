"""LiteAPI adapter: normalize a ``data/hotels`` item (+ its ``hotels/rates`` entry) to a ``Hotel``.

Per-provider normalization lives here and nowhere else. The exact field mapping is documented in
``spec/data-sources.md`` → LiteAPI to domain mapping, and verified against the recorded fixtures in
``tests/fixtures/liteapi/``. Data problems degrade (a field is dropped) rather than crash.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from importlib import resources
from typing import Any

from hotel_finder.models import GeoPoint, Hotel, normalize_amenities
from hotel_finder.utils.text import strip_html

RawRecord = dict[str, Any]

# A LiteAPI cancellation tag of "RFN" is refundable; "NRFN" is non-refundable.
_REFUNDABLE_TAG = "RFN"


@lru_cache(maxsize=1)
def _packaged_facilities() -> dict[str, str]:
    """The shipped LiteAPI facility id → English-name dictionary (slimmed, see data-sources.md)."""
    text = (resources.files("hotel_finder.providers.liteapi") / "facilities.json").read_text(
        encoding="utf-8"
    )
    data: dict[str, str] = json.loads(text)
    return data


def _offer(
    total: float, currency: str, board: str | None, refundable: bool, nights: int
) -> dict[str, Any]:
    return {
        "total": round(total, 2),
        "currency": currency,
        "per_night": round(total / nights, 2) if nights > 0 else None,
        "board": board,
        "refundable": refundable,
    }


def _rate_offers(rate_entry: RawRecord, nights: int) -> list[dict[str, Any]]:
    """Cheapest refundable + cheapest non-refundable offer for one hotel (dicts in RateOffer shape).

    Kept as plain dicts (not ``RateOffer``) so a ``Hotel`` stays JSON-serializable; the pipeline
    builds ``RateOffer`` objects from them and flags ``over_budget`` against the request budget.
    """
    cheapest: dict[bool, dict[str, Any]] = {}
    for room_type in rate_entry.get("roomTypes", []):
        for rate in room_type.get("rates", []):
            totals = (rate.get("retailRate") or {}).get("total") or []
            if not totals:
                continue
            amount = totals[0].get("amount")
            currency = totals[0].get("currency")
            if amount is None or currency is None:
                continue
            tag = (rate.get("cancellationPolicies") or {}).get("refundableTag")
            refundable = tag == _REFUNDABLE_TAG
            offer = _offer(float(amount), currency, rate.get("boardName"), refundable, nights)
            current = cheapest.get(refundable)
            if current is None or offer["total"] < current["total"]:
                cheapest[refundable] = offer
    # Refundable first, then non-refundable (deterministic order).
    return [cheapest[kind] for kind in (True, False) if kind in cheapest]


class LiteApiAdapter:
    """Normalizes LiteAPI payloads into :class:`Hotel`, attaching priced offers when rates exist."""

    source = "liteapi"

    def __init__(self, facilities: Mapping[str, str] | None = None) -> None:
        self._facilities = facilities if facilities is not None else _packaged_facilities()

    def _amenities(self, facility_ids: list[Any]) -> set[Any]:
        names = [self._facilities[str(fid)] for fid in facility_ids if str(fid) in self._facilities]
        return normalize_amenities(names)

    def to_hotel(
        self,
        raw: RawRecord,
        rate_entry: RawRecord | None = None,
        nights: int | None = None,
    ) -> Hotel:
        location = None
        lat, lon = raw.get("latitude"), raw.get("longitude")
        if lat is not None and lon is not None:
            location = GeoPoint(lat=lat, lon=lon)

        stars = raw.get("stars")
        star_rating = stars if isinstance(stars, int) and 1 <= stars <= 5 else None
        rating = raw.get("rating")
        guest_rating: float | None = None
        if isinstance(rating, int | float) and 0 <= rating <= 10:
            guest_rating = float(rating)
        reviews = raw.get("reviewCount")
        review_count = reviews if isinstance(reviews, int) and reviews >= 0 else None
        description = raw.get("hotelDescription")
        # First non-empty of main_photo / thumbnail (see data-sources.md mapping); still in raw.
        image_url = raw.get("main_photo") or raw.get("thumbnail") or None

        offers = _rate_offers(rate_entry, nights) if rate_entry and nights else []
        per_nights = [o["per_night"] for o in offers if o["per_night"] is not None]
        price_per_night = min(per_nights, default=None)

        stored_raw = {**raw}
        if offers:
            stored_raw["offers"] = offers

        return Hotel(
            id=str(raw["id"]),
            source=self.source,
            name=raw["name"],
            location=location,
            area=raw.get("city"),  # no neighborhood field; city as a coarse area
            address=raw.get("address"),
            price_per_night=price_per_night,
            currency=offers[0]["currency"] if offers else raw.get("currency"),
            rating=guest_rating,
            review_count=review_count,
            star_rating=star_rating,
            amenities=self._amenities(raw.get("facilityIds", [])),
            image_url=image_url,
            description=strip_html(description) if description else None,
            raw=stored_raw,
        )
