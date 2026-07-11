"""Cheap shortlist: ordering, truncation, desired-area bonus."""

from __future__ import annotations

from collections.abc import Callable

from hotel_finder.context import SearchContext
from hotel_finder.models import Hotel
from hotel_finder.stages.shortlist import shortlist


def test_orders_by_rating_and_truncates(make_hotel: Callable[..., Hotel]) -> None:
    hotels = [make_hotel(id=str(i), rating=r) for i, r in enumerate([6.0, 9.0, 8.0])]
    out = shortlist(hotels, SearchContext(), size=2)
    assert [h.rating for h in out] == [9.0, 8.0]


def test_desired_area_breaks_tie(make_hotel: Callable[..., Hotel]) -> None:
    in_area = make_hotel(id="a", rating=8.0, area="El Born")
    out_area = make_hotel(id="b", rating=8.0, area="Sants")
    context = SearchContext(desired_area="born")
    out = shortlist([out_area, in_area], context, size=2)
    assert out[0].id == "a"
