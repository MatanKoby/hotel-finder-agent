"""Geocoding: turn a free-text place name into coordinates + a city/country.

Used by the pipeline's resolve step (`pipeline.py`) when a `Place` gives only `text`. The backend
is free, keyless OpenStreetMap **Nominatim** (a proper `User-Agent` is required, see
`data-sources.md`). It is small and behind the `Geocoder` protocol so tests use an offline double
and a richer backend (e.g. LiteAPI place lookup) can be slotted in later.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from hotel_finder.config import Settings


class GeoResult(BaseModel):
    """What a geocoder resolved a place name to."""

    lat: float
    lon: float
    city: str | None = None
    country_code: str | None = None  # ISO-3166-1 alpha-2, upper-cased


class Geocoder(Protocol):
    """Resolves a free-text place name, or returns ``None`` when it can't."""

    async def geocode(self, text: str) -> GeoResult | None: ...


class NominatimGeocoder:
    """OpenStreetMap Nominatim backend (free, keyless; requires a descriptive User-Agent)."""

    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._timeout = timeout
        self._client = client

    async def geocode(self, text: str) -> GeoResult | None:
        params: dict[str, str | int] = {
            "q": text,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        headers = {"User-Agent": self._user_agent}
        if self._client is not None:
            response = await self._client.get(
                f"{self._base_url}/search", params=params, headers=headers
            )
            rows = response.json()
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self._base_url}/search", params=params, headers=headers
                )
                rows = response.json()
        return _first_result(rows)


def _first_result(rows: Any) -> GeoResult | None:
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    try:
        lat = float(row["lat"])
        lon = float(row["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    address = row.get("address") or {}
    city = address.get("city") or address.get("town") or address.get("village")
    country_code = address.get("country_code")
    return GeoResult(
        lat=lat,
        lon=lon,
        city=city,
        country_code=country_code.upper() if isinstance(country_code, str) else None,
    )


def make_geocoder(settings: Settings) -> Geocoder:
    """Build the configured geocoder (Nominatim)."""
    return NominatimGeocoder(
        settings.nominatim_base_url,
        settings.geocoder_user_agent,
        settings.geocoder_timeout,
    )
