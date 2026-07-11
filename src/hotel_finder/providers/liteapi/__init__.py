"""LiteAPI (Nuitée) provider: real lodging with location, description, and price.

One folder, the standard shape: ``api.py`` (HTTP calls), ``adapter.py`` (payload → ``Hotel`` +
offers), and ``provider.py`` (the two-call flow wired to a ``HotelProvider``). Field mapping is in
``spec/data-sources.md`` → LiteAPI to domain mapping. Disabled by default; enable via
``ENABLED_PROVIDERS`` once ``LITEAPI_API_KEY`` is set.
"""

from __future__ import annotations

from hotel_finder.providers.liteapi.provider import LiteApiProvider

__all__ = ["LiteApiProvider"]
