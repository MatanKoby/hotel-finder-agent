"""Provider interfaces and the default api+adapter composition.

The core pipeline depends only on :class:`HotelProvider`. Each concrete source supplies a
:class:`ProviderApi` (fetch raw records) and a :class:`HotelAdapter` (normalize one record into
our :class:`~hotel_finder.models.Hotel`); :class:`ComposedProvider` wires the two together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from hotel_finder.contracts import HotelSearchRequest
from hotel_finder.models import Hotel

# One raw record in a provider's native shape, before normalization.
RawRecord = dict[str, Any]


class ProviderApi(Protocol):
    """Fetches raw records from a single data source (HTTP API, fixtures, scraper)."""

    async def fetch(self, request: HotelSearchRequest) -> list[RawRecord]: ...


class HotelAdapter(Protocol):
    """Normalizes one source's raw record into our canonical :class:`Hotel`."""

    def to_hotel(self, raw: RawRecord) -> Hotel: ...


class HotelProvider(Protocol):
    """A data source the pipeline can query. The only provider interface the core knows about."""

    @property
    def name(self) -> str: ...

    async def search(self, request: HotelSearchRequest) -> list[Hotel]: ...


@dataclass(frozen=True)
class ComposedProvider:
    """Default provider: fetch raw via ``api``, then normalize each record via ``adapter``.

    Most providers need nothing more than this. A source requiring bespoke flow (pagination,
    multiple calls) can implement :class:`HotelProvider` directly instead.
    """

    name: str
    api: ProviderApi
    adapter: HotelAdapter

    async def search(self, request: HotelSearchRequest) -> list[Hotel]:
        raw = await self.api.fetch(request)
        return [self.adapter.to_hotel(record) for record in raw]
