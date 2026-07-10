"""Canonical model behavior: amenity normalization, provenance, validation."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from hotel_finder.models import (
    Amenity,
    GeoPoint,
    Hotel,
    normalize_amenities,
    normalize_amenity,
)


def test_normalize_amenity_maps_synonyms() -> None:
    assert normalize_amenity("Free WiFi") is Amenity.WIFI
    assert normalize_amenity("air conditioning") is Amenity.AC
    assert normalize_amenity("wifi") is Amenity.WIFI


def test_normalize_amenity_unknown_is_none() -> None:
    assert normalize_amenity("teleporter") is None
    assert normalize_amenity("") is None


def test_normalize_amenities_drops_unknown() -> None:
    assert normalize_amenities(["WiFi", "Garage", "teleporter"]) == {
        Amenity.WIFI,
        Amenity.PARKING,
    }


def test_hotel_records_provenance(make_hotel: Callable[..., Hotel]) -> None:
    hotel = make_hotel(source="mock")
    assert hotel.sources == ["mock"]


def test_geopoint_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        GeoPoint(lat=100.0, lon=0.0)
