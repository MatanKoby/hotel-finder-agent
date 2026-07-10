"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from hotel_finder.config import Settings
from hotel_finder.models import Hotel


@pytest.fixture
def make_hotel() -> Callable[..., Hotel]:
    """Factory for Hotel instances with sensible defaults; override any field via kwargs."""

    def _make(**overrides: object) -> Hotel:
        data: dict[str, object] = {"id": "h", "source": "mock", "name": "Hotel"}
        data.update(overrides)
        return Hotel(**data)

    return _make


@pytest.fixture
def settings() -> Settings:
    """Hermetic settings: ignore any developer .env, default to the offline heuristic scorer."""
    return Settings(_env_file=None, scorer="heuristic", enabled_providers=["mock"])
