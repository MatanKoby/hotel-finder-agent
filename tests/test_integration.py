"""Submodule integration surface: exports, no-mandatory-config, and the runnable example."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

import hotel_finder as hf
from hotel_finder import (
    HotelSearchRequest,
    HotelSearchResponse,
    Place,
    Settings,
    search_sync,
)

_ROOT = Path(__file__).resolve().parent.parent

_EXPECTED_EXPORTS = {
    "search", "search_sync",
    "HotelSearchRequest", "HotelSearchResponse",
    "Place", "Stay", "Occupancy", "Filters",
    "Pick", "RateOffer", "ResolvedQuery", "Diagnostics",
    "Intent", "LensName", "Settings",
    "Hotel", "GeoPoint", "Amenity", "PriceBand",
}


def _load_example() -> ModuleType:
    path = _ROOT / "examples" / "orchestrator_sim.py"
    spec = importlib.util.spec_from_file_location("orchestrator_sim", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_api_is_exported() -> None:
    for name in _EXPECTED_EXPORTS:
        assert hasattr(hf, name), f"missing export: {name}"
        assert name in hf.__all__, f"missing from __all__: {name}"


def test_importing_needs_no_keys_or_env() -> None:
    settings = Settings(_env_file=None)
    assert settings.liteapi_api_key == ""
    assert settings.llm_api_key == ""
    assert settings.nebius_endpoint_url == ""
    assert settings.enabled_providers == ["mock"]
    assert settings.scorer == "heuristic"


def test_offline_mock_search_runs() -> None:
    response = search_sync(
        HotelSearchRequest(place=Place(city="Barcelona")),
        Settings(_env_file=None, enabled_providers=["mock"]),
    )
    assert isinstance(response, HotelSearchResponse)
    assert response.agent_status == "ok"
    assert any(picks for picks in response.lenses.values())


def test_enabled_providers_parse_from_env_string(monkeypatch: pytest.MonkeyPatch) -> None:
    # ENABLED_PROVIDERS is a plain (comma-separated) string in the environment, not JSON.
    monkeypatch.setenv("ENABLED_PROVIDERS", "mock,liteapi")
    assert Settings(_env_file=None).enabled_providers == ["mock", "liteapi"]
    monkeypatch.setenv("ENABLED_PROVIDERS", "liteapi")
    assert Settings(_env_file=None).enabled_providers == ["liteapi"]


def test_example_orchestrator_sim_runs_offline() -> None:
    example = _load_example()
    response = example.run(
        Settings(_env_file=None, enabled_providers=["mock"], scorer="heuristic")
    )
    assert isinstance(response, HotelSearchResponse)
    assert any(picks for picks in response.lenses.values())
