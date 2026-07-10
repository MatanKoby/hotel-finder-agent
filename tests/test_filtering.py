"""Hard filter: amenities, price bounds, and area radius."""

from __future__ import annotations

from collections.abc import Callable

from hotel_finder.models import Amenity, GeoPoint, Hotel
from hotel_finder.stages.filtering import FilterCriteria, hard_filter, passes


def test_requires_must_have_amenities(make_hotel: Callable[..., Hotel]) -> None:
    hotel = make_hotel(amenities={Amenity.WIFI})
    assert passes(hotel, FilterCriteria(must_have_amenities=frozenset({Amenity.WIFI})))
    assert not passes(hotel, FilterCriteria(must_have_amenities=frozenset({Amenity.POOL})))


def test_price_bounds(make_hotel: Callable[..., Hotel]) -> None:
    hotel = make_hotel(price_per_night=100.0)
    assert passes(hotel, FilterCriteria(price_max=150.0))
    assert not passes(hotel, FilterCriteria(price_max=80.0))
    assert not passes(hotel, FilterCriteria(price_min=120.0))


def test_unknown_price_excluded_when_bound_set(make_hotel: Callable[..., Hotel]) -> None:
    hotel = make_hotel(price_per_night=None)
    assert not passes(hotel, FilterCriteria(price_max=150.0))


def test_area_radius(make_hotel: Callable[..., Hotel]) -> None:
    center = GeoPoint(lat=41.3874, lon=2.1686)
    near = make_hotel(id="near", location=GeoPoint(lat=41.388, lon=2.169))
    far = make_hotel(id="far", location=GeoPoint(lat=41.5, lon=2.4))
    criteria = FilterCriteria(center=center, radius_km=2.0)
    assert hard_filter([near, far], criteria) == [near]
