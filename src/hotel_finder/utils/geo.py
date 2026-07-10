"""Geographic helpers. The single home for distance math in the codebase."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from hotel_finder.models import GeoPoint

EARTH_RADIUS_KM = 6371.0088


def haversine(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two points, in kilometers."""
    lat1, lon1, lat2, lon2 = map(radians, (a.lat, a.lon, b.lat, b.lon))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))
