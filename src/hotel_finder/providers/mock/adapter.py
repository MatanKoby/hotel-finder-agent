"""Mock provider adapter: maps a raw fixture record into our canonical :class:`Hotel`.

Per-provider normalization lives here and nowhere else — including amenity-vocab mapping and
parsing the source's native field names. (Price-band *derivation* from a bare price is a global
policy and happens in the pipeline using configured thresholds.)
"""

from __future__ import annotations

from hotel_finder.models import GeoPoint, Hotel, PriceBand, normalize_amenities
from hotel_finder.providers.base import RawRecord


class MockAdapter:
    """Normalizes raw fixture records (already close to our shape) into :class:`Hotel`."""

    source = "mock"

    def to_hotel(self, raw: RawRecord) -> Hotel:
        location = None
        if raw.get("lat") is not None and raw.get("lon") is not None:
            location = GeoPoint(lat=raw["lat"], lon=raw["lon"])

        price_band = PriceBand(raw["price_band"]) if raw.get("price_band") else None

        return Hotel(
            id=str(raw["id"]),
            source=self.source,
            name=raw["name"],
            location=location,
            area=raw.get("area"),
            address=raw.get("address"),
            price_per_night=raw.get("price_per_night"),
            currency=raw.get("currency"),
            price_band=price_band,
            rating=raw.get("rating"),
            review_count=raw.get("review_count"),
            star_rating=raw.get("star_rating"),
            amenities=normalize_amenities(raw.get("amenities", [])),
            url=raw.get("url"),
            description=raw.get("description"),
            raw=raw,
        )
