"""LiteAPI provider: adapter mapping from recorded fixtures + the two-call join (all offline).

No network: the adapter is driven from the recorded Barcelona `data/hotels` + `hotels/rates`
captures in `tests/fixtures/liteapi/`, and the provider/pipeline paths use a stubbed client.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from hotel_finder.config import Settings
from hotel_finder.contracts import Filters, HotelSearchRequest, LensName, Place, Stay
from hotel_finder.models import Amenity
from hotel_finder.pipeline import search
from hotel_finder.providers.liteapi import provider as liteapi_provider
from hotel_finder.providers.liteapi.adapter import LiteApiAdapter
from hotel_finder.providers.liteapi.provider import LiteApiProvider

_FIX = Path(__file__).parent / "fixtures" / "liteapi"


def _load(name: str) -> Any:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def facilities() -> dict[str, str]:
    return _load("data_facilities.json")


@pytest.fixture
def hotels_payload() -> dict[str, Any]:
    return _load("data_hotels_barcelona.json")


@pytest.fixture
def rates_payload() -> dict[str, Any]:
    return _load("hotels_rates_barcelona.json")


def _adapt_all(
    adapter: LiteApiAdapter, hotels_payload: dict[str, Any], rates_payload: dict[str, Any]
) -> dict[str, Any]:
    rates_by = {e["hotelId"]: e for e in rates_payload["data"]}
    hotels = [
        adapter.to_hotel(h, rates_by.get(h["id"]), nights=3) for h in hotels_payload["data"]
    ]
    return {h.id: h for h in hotels}


def test_adapter_maps_content_fields(
    facilities: dict[str, str], hotels_payload: dict[str, Any], rates_payload: dict[str, Any]
) -> None:
    by_id = _adapt_all(LiteApiAdapter(facilities=facilities), hotels_payload, rates_payload)

    seventy = by_id["lp27a0d8"]
    assert seventy.name == "Seventy Barcelona"
    assert seventy.source == "liteapi"
    assert seventy.location is not None
    assert seventy.star_rating == 4
    assert seventy.rating == 9.8  # guest score kept on the 0-10 scale
    assert seventy.review_count == 3940
    assert seventy.description and "<" not in seventy.description  # HTML stripped
    assert {Amenity.WIFI, Amenity.AC} <= seventy.amenities  # facilityIds -> vocab


def test_adapter_builds_priced_offers(
    facilities: dict[str, str], hotels_payload: dict[str, Any], rates_payload: dict[str, Any]
) -> None:
    by_id = _adapt_all(LiteApiAdapter(facilities=facilities), hotels_payload, rates_payload)

    all_offers = [o for h in by_id.values() for o in h.raw.get("offers", [])]
    assert all_offers
    for offer in all_offers:
        assert offer["total"] > 0
        assert offer["currency"] == "EUR"
        assert isinstance(offer["refundable"], bool)
        assert offer["per_night"] == round(offer["total"] / 3, 2)

    # The recorded set covers both cancellation kinds (RFN -> True, NRFN -> False).
    assert {o["refundable"] for o in all_offers} == {True, False}

    # price_per_night is the cheapest offer's per-night.
    seventy = by_id["lp27a0d8"]
    assert seventy.price_per_night == min(o["per_night"] for o in seventy.raw["offers"])


def test_adapter_content_only_has_no_offers(
    facilities: dict[str, str], hotels_payload: dict[str, Any]
) -> None:
    adapter = LiteApiAdapter(facilities=facilities)
    hotel = adapter.to_hotel(hotels_payload["data"][0], None, None)
    assert not hotel.raw.get("offers")
    assert hotel.price_per_night is None
    assert hotel.description  # content is still there


class _FakeClient:
    """Stubs LiteApiClient: returns the recorded payloads instead of hitting the network."""

    payloads: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def data_hotels(self, **kwargs: Any) -> dict[str, Any]:
        return self.payloads["hotels"]

    async def hotels_rates(self, **kwargs: Any) -> dict[str, Any]:
        return self.payloads["rates"]


def _stub_client(
    monkeypatch: pytest.MonkeyPatch, hotels_payload: dict[str, Any], rates_payload: dict[str, Any]
) -> None:
    _FakeClient.payloads = {"hotels": hotels_payload, "rates": rates_payload}
    monkeypatch.setattr(liteapi_provider, "LiteApiClient", _FakeClient)


def _stay() -> Stay:
    return Stay(check_in=date(2026, 8, 1), check_out=date(2026, 8, 4))  # 3 nights


async def test_provider_joins_content_and_rates(
    monkeypatch: pytest.MonkeyPatch, hotels_payload: dict[str, Any], rates_payload: dict[str, Any]
) -> None:
    _stub_client(monkeypatch, hotels_payload, rates_payload)
    settings = Settings(_env_file=None, liteapi_api_key="sand_test")
    request = HotelSearchRequest(place=Place(country_code="ES", city="Barcelona"), stay=_stay())

    hotels = await LiteApiProvider(settings).search(request)

    assert len(hotels) == 4
    assert all(h.source == "liteapi" for h in hotels)
    assert [h for h in hotels if h.raw.get("offers")]  # rates joined onto hotels


async def test_provider_without_key_raises() -> None:
    settings = Settings(_env_file=None, liteapi_api_key="")
    request = HotelSearchRequest(place=Place(city="Barcelona"))
    with pytest.raises(RuntimeError):
        await LiteApiProvider(settings).search(request)


async def test_pipeline_end_to_end_over_liteapi_stub(
    monkeypatch: pytest.MonkeyPatch, hotels_payload: dict[str, Any], rates_payload: dict[str, Any]
) -> None:
    _stub_client(monkeypatch, hotels_payload, rates_payload)
    settings = Settings(
        _env_file=None,
        scorer="heuristic",
        enabled_providers=["liteapi"],
        liteapi_api_key="sand_test",
        min_candidates=8,
    )
    # Budget below the cheapest few forces the budget-too-low fallback.
    request = HotelSearchRequest(
        place=Place(country_code="ES", city="Barcelona"),
        stay=_stay(),
        filters=Filters(price_max=90.0),
    )
    response = await search(request, settings)

    assert response.diagnostics.providers_used == ["liteapi"]
    priced = [p for picks in response.lenses.values() for p in picks if p.offers]
    assert priced  # real rates surface as offers on the picks

    all_offers = [o for picks in response.lenses.values() for p in picks for o in p.offers]
    assert any(o.over_budget for o in all_offers)
    assert response.agent_status == "degraded"
    assert any("within EUR 90" in w for w in response.warnings)


async def test_pipeline_refundable_filter_over_liteapi_stub(
    monkeypatch: pytest.MonkeyPatch, hotels_payload: dict[str, Any], rates_payload: dict[str, Any]
) -> None:
    _stub_client(monkeypatch, hotels_payload, rates_payload)
    settings = Settings(
        _env_file=None, scorer="heuristic", enabled_providers=["liteapi"], liteapi_api_key="k"
    )
    request = HotelSearchRequest(
        place=Place(country_code="ES", city="Barcelona"),
        stay=_stay(),
        filters=Filters(refundable=True),
    )
    response = await search(request, settings)

    offers = [
        o for picks in response.lenses.values() for p in picks for o in p.offers
    ]
    # Only the refundable rate kind survives the filter.
    assert offers
    assert all(o.refundable for o in offers)
    assert LensName.OVERALL_STANDOUTS in response.lenses
