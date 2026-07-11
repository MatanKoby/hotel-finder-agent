"""Provider registry: build enabled providers by name.

Providers are registered as **factories** (``Settings -> HotelProvider``) because a real source
needs credentials/endpoints from config (e.g. LiteAPI's key). The pipeline resolves the enabled
providers here, passing the effective settings. Adding a source = build its folder under
``providers/`` and register its factory here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from hotel_finder.config import Settings
from hotel_finder.providers.base import ComposedProvider, HotelProvider
from hotel_finder.providers.liteapi import LiteApiProvider
from hotel_finder.providers.mock.adapter import MockAdapter
from hotel_finder.providers.mock.api import MockApi

ProviderFactory = Callable[[Settings], HotelProvider]

_REGISTRY: dict[str, ProviderFactory] = {}


def register(name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under ``name``."""
    _REGISTRY[name] = factory


def get_provider(name: str, settings: Settings) -> HotelProvider:
    """Build the registered provider for ``name`` (raises ``KeyError`` if unknown)."""
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown provider {name!r}; registered: {sorted(_REGISTRY)}") from None
    return factory(settings)


def get_providers(names: Iterable[str], settings: Settings) -> list[HotelProvider]:
    """Build several providers by name with the effective settings."""
    return [get_provider(name, settings) for name in names]


# --- built-in providers ---
register("mock", lambda _settings: ComposedProvider("mock", MockApi(), MockAdapter()))
register("liteapi", LiteApiProvider)
