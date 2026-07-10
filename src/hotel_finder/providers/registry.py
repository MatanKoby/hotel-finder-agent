"""Provider registry: look providers up by name. The pipeline resolves enabled providers here.

Built-in providers register themselves at import time. Adding a source = build its folder under
``providers/`` and register it here.
"""

from __future__ import annotations

from collections.abc import Iterable

from hotel_finder.providers.base import ComposedProvider, HotelProvider
from hotel_finder.providers.mock.adapter import MockAdapter
from hotel_finder.providers.mock.api import MockApi

_REGISTRY: dict[str, HotelProvider] = {}


def register(provider: HotelProvider) -> None:
    """Register a provider under its ``name``."""
    _REGISTRY[provider.name] = provider


def get_provider(name: str) -> HotelProvider:
    """Return the registered provider for ``name`` (raises ``KeyError`` if unknown)."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown provider {name!r}; registered: {sorted(_REGISTRY)}") from None


def get_providers(names: Iterable[str]) -> list[HotelProvider]:
    """Resolve several provider names to their instances."""
    return [get_provider(name) for name in names]


# --- built-in providers ---
register(ComposedProvider(name="mock", api=MockApi(), adapter=MockAdapter()))
