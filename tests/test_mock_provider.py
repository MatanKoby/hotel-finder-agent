"""The mock provider loads fixtures and its adapter normalizes them into Hotels."""

from __future__ import annotations

from hotel_finder.contracts import HotelQuery
from hotel_finder.models import Amenity
from hotel_finder.providers.registry import get_provider


async def test_loads_all_fixtures() -> None:
    hotels = await get_provider("mock").search(HotelQuery(location="Barcelona"))
    assert len(hotels) == 14
    assert all(h.source == "mock" for h in hotels)


async def test_adapter_normalizes_amenities_and_fields() -> None:
    hotels = await get_provider("mock").search(HotelQuery(location="Barcelona"))
    by_id = {h.id: h for h in hotels}

    palace = by_id["bcn-008"]
    assert {Amenity.POOL, Amenity.AIRPORT_SHUTTLE, Amenity.SPA} <= palace.amenities
    assert all(isinstance(a, Amenity) for a in palace.amenities)

    gem = by_id["bcn-011"]
    assert gem.rating == 4.9
    assert gem.review_count == 38
