"""Geocoding: Nominatim parsing (stubbed transport) + the pipeline resolve step (offline double)."""

from __future__ import annotations

import httpx
import pytest

from hotel_finder import pipeline
from hotel_finder.config import Settings
from hotel_finder.contracts import HotelSearchRequest, Place
from hotel_finder.pipeline import search
from hotel_finder.utils.geocode import GeoResult, NominatimGeocoder


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"scorer": "heuristic", "enabled_providers": ["mock"]}
    base.update(overrides)
    return Settings(_env_file=None, **base)


async def test_nominatim_parses_first_result() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "lat": "41.3825",
                    "lon": "2.1769",
                    "address": {"city": "Barcelona", "country_code": "es"},
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    geo = NominatimGeocoder("https://nominatim.test", "ua/1.0", client=client)
    result = await geo.geocode("Barcelona old town")
    await client.aclose()

    assert result is not None
    assert (round(result.lat, 4), round(result.lon, 4)) == (41.3825, 2.1769)
    assert result.city == "Barcelona"
    assert result.country_code == "ES"  # upper-cased


async def test_nominatim_empty_result_is_none() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=[]))
    )
    geo = NominatimGeocoder("https://nominatim.test", "ua/1.0", client=client)
    result = await geo.geocode("nowhere at all")
    await client.aclose()
    assert result is None


class _FakeGeocoder:
    def __init__(self, result: GeoResult | Exception | None) -> None:
        self._result = result

    async def geocode(self, text: str) -> GeoResult | None:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


async def test_text_place_is_geocoded(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeGeocoder(GeoResult(lat=41.3825, lon=2.1769, city="Barcelona", country_code="ES"))
    monkeypatch.setattr(pipeline, "make_geocoder", lambda _settings: fake)

    request = HotelSearchRequest(place=Place(text="Barcelona city centre"))
    response = await search(request, _settings())

    assert response.resolved.center is not None
    assert response.resolved.city == "Barcelona"
    assert any(picks for picks in response.lenses.values())  # still returns results


async def test_geocode_failure_warns_not_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeGeocoder(RuntimeError("boom"))
    monkeypatch.setattr(pipeline, "make_geocoder", lambda _settings: fake)

    request = HotelSearchRequest(place=Place(text="Barcelona"))
    response = await search(request, _settings())

    assert response.resolved.center is None
    assert any("geocoding" in w.lower() for w in response.warnings)
    assert response.agent_status == "degraded"


async def test_geocode_no_result_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "make_geocoder", lambda _settings: _FakeGeocoder(None))

    request = HotelSearchRequest(place=Place(text="asdfghjkl"))
    response = await search(request, _settings())

    assert response.resolved.center is None
    assert any("could not geocode" in w for w in response.warnings)


async def test_structured_place_skips_geocoding(monkeypatch: pytest.MonkeyPatch) -> None:
    # A structured place with no desired_area must not invoke the geocoder at all.
    def _boom(_settings: Settings) -> object:
        raise AssertionError("geocoder should not be built for a structured place")

    monkeypatch.setattr(pipeline, "make_geocoder", _boom)
    request = HotelSearchRequest(place=Place(city="Barcelona"))
    response = await search(request, _settings())
    assert response.resolved.city == "Barcelona"


async def test_desired_area_geocoded_to_ranking_point(monkeypatch: pytest.MonkeyPatch) -> None:
    # A structured city + desired_area geocodes the neighbourhood into resolved.center, so located
    # picks carry distance_to_desired_km — without a warning (a soft bias, not a degrade).
    fake = _FakeGeocoder(GeoResult(lat=41.385, lon=2.181, city="Barcelona", country_code="ES"))
    monkeypatch.setattr(pipeline, "make_geocoder", lambda _settings: fake)

    request = HotelSearchRequest(place=Place(city="Barcelona", desired_area="El Born"))
    response = await search(request, _settings(geocode_desired_area=True))

    assert response.resolved.center is not None
    assert response.resolved.area == "El Born"
    located = [p for plist in response.lenses.values() for p in plist if p.coordinates is not None]
    assert located and all(p.distance_to_desired_km is not None for p in located)
    assert not response.warnings and response.agent_status == "ok"


async def test_desired_area_geocoding_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    # With geocode_desired_area off, a structured place never builds a geocoder (offline-safe).
    def _boom(_settings: Settings) -> object:
        raise AssertionError("geocoder should not be built when geocode_desired_area is off")

    monkeypatch.setattr(pipeline, "make_geocoder", _boom)
    request = HotelSearchRequest(place=Place(city="Barcelona", desired_area="El Born"))
    response = await search(request, _settings(geocode_desired_area=False))
    assert response.resolved.center is None  # no ranking point, falls back to the area string
