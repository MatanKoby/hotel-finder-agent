"""Cross-provider merge + dedupe."""

from __future__ import annotations

from collections.abc import Callable

from hotel_finder.models import Amenity, GeoPoint, Hotel
from hotel_finder.stages.dedupe import dedupe


def test_merges_same_hotel_from_two_providers(make_hotel: Callable[..., Hotel]) -> None:
    a = make_hotel(
        id="a1",
        source="src_a",
        name="Hotel Sol",
        location=GeoPoint(lat=41.0, lon=2.0),
        amenities={Amenity.WIFI},
        rating=4.0,
    )
    b = make_hotel(
        id="b1",
        source="src_b",
        name="hotel  sol",  # normalizes equal
        location=GeoPoint(lat=41.0001, lon=2.0001),  # ~15 m away
        amenities={Amenity.POOL},
        price_per_night=100.0,
    )

    merged = dedupe([a, b])
    assert len(merged) == 1
    result = merged[0]
    assert result.amenities == {Amenity.WIFI, Amenity.POOL}
    assert set(result.sources) == {"src_a", "src_b"}
    assert result.price_per_night == 100.0  # filled from b
    assert result.rating == 4.0  # kept from a (primary)


def test_distinct_names_not_merged(make_hotel: Callable[..., Hotel]) -> None:
    a = make_hotel(id="a", name="Alpha")
    b = make_hotel(id="b", name="Beta")
    assert len(dedupe([a, b])) == 2


def test_same_name_far_apart_not_merged(make_hotel: Callable[..., Hotel]) -> None:
    a = make_hotel(id="a", name="Sol", location=GeoPoint(lat=41.0, lon=2.0))
    b = make_hotel(id="b", name="Sol", location=GeoPoint(lat=42.0, lon=3.0))
    assert len(dedupe([a, b])) == 2
