"""Cheap shortlist: ordering, truncation, desired-area bonus."""

from __future__ import annotations

from collections.abc import Callable

from hotel_finder.contracts import HotelQuery
from hotel_finder.models import Hotel
from hotel_finder.stages.shortlist import shortlist


def test_orders_by_rating_and_truncates(make_hotel: Callable[..., Hotel]) -> None:
    hotels = [make_hotel(id=str(i), rating=r) for i, r in enumerate([3.0, 4.5, 4.0])]
    out = shortlist(hotels, HotelQuery(location="X"), size=2)
    assert [h.rating for h in out] == [4.5, 4.0]


def test_desired_area_breaks_tie(make_hotel: Callable[..., Hotel]) -> None:
    in_area = make_hotel(id="a", rating=4.0, area="El Born")
    out_area = make_hotel(id="b", rating=4.0, area="Sants")
    query = HotelQuery(location="X", desired_area="born")
    out = shortlist([out_area, in_area], query, size=2)
    assert out[0].id == "a"
