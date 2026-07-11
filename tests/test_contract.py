"""The submodule contract validates hard at construction (the orchestrator's shared validator).

These are the only errors this repo raises: malformed input, caught before ``search()`` runs.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from hotel_finder.contracts import Filters, HotelSearchRequest, Place, Stay


def test_valid_request_builds_with_defaults() -> None:
    request = HotelSearchRequest(place=Place(city="Barcelona", country_code="ES"))
    assert request.request_id  # auto uuid
    assert request.stay is None
    assert request.picks_per_lens == 3
    assert request.lenses is None  # all three


def test_place_requires_a_usable_path() -> None:
    with pytest.raises(ValidationError):
        Place(country_code="ES")  # no city / center / text


def test_stay_rejects_checkout_not_after_checkin() -> None:
    with pytest.raises(ValidationError):
        Stay(check_in=date(2026, 8, 4), check_out=date(2026, 8, 1))


def test_filters_reject_inverted_price_range() -> None:
    with pytest.raises(ValidationError):
        Filters(price_min=200.0, price_max=100.0)


def test_filters_reject_out_of_range_rating() -> None:
    with pytest.raises(ValidationError):
        Filters(min_guest_rating=11.0)


def test_request_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        HotelSearchRequest(place=Place(city="Barcelona"), destination="typo")  # type: ignore[call-arg]


def test_request_requires_place() -> None:
    with pytest.raises(ValidationError):
        HotelSearchRequest()  # type: ignore[call-arg]
