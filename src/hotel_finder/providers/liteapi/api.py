"""LiteAPI HTTP layer: discovery + content (``data/hotels``) and prices (``hotels/rates``).

A thin async client over ``httpx``. It returns the raw JSON payloads unchanged; normalization into
our domain types lives in ``adapter.py``. Auth is the ``X-API-Key`` header (see ``config.md``).
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from hotel_finder.contracts import Occupancy, Stay


class LiteApiClient:
    """Async client for the two LiteAPI calls Milestone 1 needs. Use as an async context manager."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={
                "X-API-Key": api_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
        )

    async def __aenter__(self) -> LiteApiClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def data_hotels(
        self,
        *,
        country_code: str | None = None,
        city: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Discovery + static content. Query by country+city, or by coordinates + radius."""
        params: dict[str, Any] = {"limit": limit}
        if country_code:
            params["countryCode"] = country_code
        if city:
            params["cityName"] = city
        if latitude is not None and longitude is not None:
            params["latitude"] = latitude
            params["longitude"] = longitude
            if radius_km is not None:
                params["radius"] = int(radius_km * 1000)  # LiteAPI radius is in meters
        response = await self._client.get("/data/hotels", params=params)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload

    async def hotels_rates(
        self,
        *,
        hotel_ids: list[str],
        stay: Stay,
        rooms: list[Occupancy],
        guest_nationality: str,
    ) -> dict[str, Any]:
        """Real per-hotel rates for the given ids, stay dates, rooms, and traveler nationality.

        ``rooms`` and ``guest_nationality`` are supplied by the caller (the provider derives rooms
        from ``request.guests`` when ``stay.rooms`` is ``None``, and reads the trip-level
        ``guest_nationality``) rather than read off ``Stay``, since those are trip-level now."""
        body: dict[str, Any] = {
            "hotelIds": hotel_ids,
            "checkin": stay.check_in.isoformat(),
            "checkout": stay.check_out.isoformat(),
            "currency": stay.currency,
            "guestNationality": guest_nationality,
            "occupancies": [
                {"adults": room.adults, "children": list(room.children_ages)}
                for room in rooms
            ],
        }
        response = await self._client.post("/hotels/rates", json=body)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload
