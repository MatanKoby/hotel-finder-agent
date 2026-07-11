"""The LiteAPI provider: discovery + content, then rates, combined into ``Hotel`` records.

Not a :class:`ComposedProvider` because it needs two calls (``data/hotels`` then ``hotels/rates``)
and joins them per hotel. Prices are fetched only when the request carries a ``stay``. Upstream
errors propagate to the pipeline's ``gather``, which turns them into ``warnings`` (never fatal).
"""

from __future__ import annotations

from typing import Any

from hotel_finder.config import Settings
from hotel_finder.contracts import HotelSearchRequest
from hotel_finder.models import Hotel
from hotel_finder.providers.liteapi.adapter import LiteApiAdapter
from hotel_finder.providers.liteapi.api import LiteApiClient


class LiteApiProvider:
    """Real hotels, content, and prices from LiteAPI (Nuitée)."""

    name = "liteapi"

    def __init__(self, settings: Settings, adapter: LiteApiAdapter | None = None) -> None:
        self._settings = settings
        self._adapter = adapter or LiteApiAdapter()

    async def search(self, request: HotelSearchRequest) -> list[Hotel]:
        if not self._settings.liteapi_api_key:
            raise RuntimeError("LITEAPI_API_KEY is not set")

        place = request.place
        async with LiteApiClient(
            self._settings.liteapi_api_key,
            self._settings.liteapi_base_url,
            self._settings.liteapi_timeout,
        ) as client:
            discovery = await client.data_hotels(
                country_code=place.country_code,
                city=place.city,
                latitude=place.center.lat if place.center else None,
                longitude=place.center.lon if place.center else None,
                radius_km=place.radius_km,
            )
            hotels_raw = discovery.get("data", [])
            hotel_ids = discovery.get("hotelIds") or [h["id"] for h in hotels_raw]

            rates_by_hotel: dict[str, dict[str, Any]] = {}
            nights: int | None = None
            if request.stay is not None and hotel_ids:
                nights = (request.stay.check_out - request.stay.check_in).days
                rates = await client.hotels_rates(hotel_ids=hotel_ids, stay=request.stay)
                for entry in rates.get("data", []):
                    rates_by_hotel[entry["hotelId"]] = entry

        return [
            self._adapter.to_hotel(raw, rates_by_hotel.get(raw["id"]), nights)
            for raw in hotels_raw
        ]
