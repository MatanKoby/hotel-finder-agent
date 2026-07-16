"""Refinement (feedback loop): stages/refine.py units + refine() end to end over the mock provider.

Offline only (mock provider + heuristic scorer), so these run under `make check`. The live path is
validated via `make eval` (the repo has no live pytest tests). Fixture hotels are the 14 Barcelona
records in providers/mock/fixtures/barcelona.json.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hotel_finder.config import Settings
from hotel_finder.context import Preference, PreferenceItem
from hotel_finder.contracts import (
    HotelFeedback,
    HotelRefineRequest,
    HotelSearchRequest,
    LensName,
    Place,
)
from hotel_finder.models import Amenity, GeoPoint, Hotel
from hotel_finder.pipeline import refine, refine_sync, search
from hotel_finder.scoring.base import ScoredHotel
from hotel_finder.stages.refine import (
    apply_preference,
    match_feedback,
    pick_id,
    plan_refine,
    refine_envelope,
)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"scorer": "heuristic", "enabled_providers": ["mock"]}
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _hotel(hid: str, name: str, **fields: object) -> Hotel:
    return Hotel(id=hid, source="mock", name=name, **fields)  # type: ignore[arg-type]


def _scored(hotel: Hotel, score: float) -> ScoredHotel:
    return ScoredHotel(hotel=hotel, score=score, subscores={"value": score}, rationale="")


# --- identity + matching ---------------------------------------------------------------------


def test_pick_id_is_source_and_id() -> None:
    assert pick_id(_hotel("bcn-007", "Diagonal")) == "mock:bcn-007"


def test_match_feedback_by_id_wins() -> None:
    hotels = [_hotel("bcn-007", "Diagonal Upscale Suites"), _hotel("bcn-001", "Hostal Gòtic Sol")]
    assert match_feedback(hotels, HotelFeedback(id="mock:bcn-007")) is hotels[0]


def test_match_feedback_name_fallback_when_no_id() -> None:
    hotels = [_hotel("1", "Hotel Arts Barcelona")]
    # unique containment, same matcher as intent=anchor
    assert match_feedback(hotels, HotelFeedback(name="Hotel Arts")) is hotels[0]


def test_match_feedback_none_on_miss_or_empty() -> None:
    hotels = [_hotel("1", "Foo Hotel")]
    assert match_feedback(hotels, HotelFeedback(id="mock:nope")) is None  # id miss, no name
    assert match_feedback(hotels, HotelFeedback()) is None  # nothing to match on


# --- wanted envelope -------------------------------------------------------------------------


def test_refine_envelope_from_wanted_items() -> None:
    items = [
        PreferenceItem(
            price_per_night=200.0, star_rating=4, rating=9.0, location=GeoPoint(lat=41.39, lon=2.16)
        ),
        PreferenceItem(
            price_per_night=300.0, star_rating=5, rating=9.4, location=GeoPoint(lat=41.41, lon=2.18)
        ),
    ]
    env = refine_envelope(items, _settings())
    assert env.price_min == 140.0 and env.price_max == 420.0  # 200*0.7 / 300*1.4
    assert env.min_star == 3  # min(4,5) - 1
    assert env.min_guest_rating == 8.0  # min(9.0,9.4) - 1.0
    assert env.center == GeoPoint(lat=41.40, lon=2.17) and env.radius_km == 3.0
    assert not env.is_empty()


def test_refine_envelope_empty_without_wanted() -> None:
    assert refine_envelope([], _settings()).is_empty()


# --- preference bias -------------------------------------------------------------------------


def test_apply_preference_favors_wanted_and_penalizes_unwanted() -> None:
    s = _settings()
    pref = Preference(
        wanted=(
            PreferenceItem(
                area="Eixample", price_per_night=250.0, star_rating=4,
                amenities=frozenset({Amenity.POOL}),
            ),
        ),
        unwanted=(PreferenceItem(area="Sants", price_per_night=60.0, star_rating=2),),
    )
    like = _scored(
        _hotel(
            "a", "Like", area="Eixample", price_per_night=240.0, star_rating=4,
            amenities={Amenity.POOL},
        ),
        0.5,
    )
    dislike = _scored(
        _hotel("b", "Dislike", area="Sants", price_per_night=62.0, star_rating=2), 0.5
    )
    out = {h.hotel.id: h for h in apply_preference([like, dislike], pref, s)}

    assert out["a"].score > 0.5 and out["a"].subscores["preference"] > 0.0  # matches wanted
    assert out["b"].score < 0.5 and out["b"].subscores["preference"] < 0.0  # matches unwanted


def test_apply_preference_noop_without_signal() -> None:
    s = _settings()
    scored = [_scored(_hotel("a", "A", area="Eixample", price_per_night=100.0), 0.5)]
    out = apply_preference(scored, Preference(), s)
    assert out[0].score == 0.5 and "preference" not in out[0].subscores


# --- plan (exclusion) ------------------------------------------------------------------------


def test_plan_refine_excludes_wanted_unwanted_and_exclude() -> None:
    cands = [_hotel("a", "Alpha"), _hotel("b", "Bravo"), _hotel("c", "Charlie")]
    request = HotelRefineRequest(
        base=HotelSearchRequest(place=Place(city="Barcelona")),
        wanted=[HotelFeedback(id="mock:a")],
        unwanted=[HotelFeedback(name="Bravo")],  # resolves by name
        exclude=["mock:c"],
    )
    plan = plan_refine(cands, request, _settings())
    assert plan.exclude_ids == frozenset({"mock:a", "mock:b", "mock:c"})


# --- contract validation ---------------------------------------------------------------------


def test_refine_request_rejects_round_below_one() -> None:
    with pytest.raises(ValidationError):
        HotelRefineRequest(base=HotelSearchRequest(place=Place(city="X")), round=0)


def test_feedback_is_forgiving_of_extra_keys() -> None:
    fb = HotelFeedback.model_validate({"id": "mock:x", "name": "X", "bogus": 123})
    assert fb.id == "mock:x" and fb.name == "X"


# --- end to end over the mock provider -------------------------------------------------------

_BASE = HotelSearchRequest(place=Place(city="Barcelona"))


async def test_refine_excludes_unwanted_property() -> None:
    request = HotelRefineRequest(
        base=_BASE, unwanted=[HotelFeedback(id="mock:bcn-008", name="Passeig Luxury Palace")]
    )
    response = await refine(request, _settings())

    names = {p.name for picks in response.lenses.values() for p in picks}
    assert "Passeig Luxury Palace" not in names
    assert response.diagnostics.refined is True and response.diagnostics.round == 1
    # every pick carries the stable "{source}:{id}" identity
    assert all(p.id.startswith("mock:") for picks in response.lenses.values() for p in picks)


async def test_refine_wanted_favors_similar_and_drops_the_wanted() -> None:
    request = HotelRefineRequest(
        base=_BASE,
        wanted=[
            HotelFeedback(id="mock:bcn-002", name="Eixample Central Rooms"),  # 88 budget 3-star
            HotelFeedback(id="mock:bcn-004", name="Gràcia Garden Hotel"),  # 130 midrange 3-star
        ],
    )
    # min_candidates=1 so the wanted envelope holds exactly (no widening).
    response = await refine(request, _settings(min_candidates=1))
    picks = [p for picks in response.lenses.values() for p in picks]
    names = {p.name for p in picks}

    assert picks  # new options were found, not an empty result
    assert response.diagnostics.widened is False
    # the wanted hotels seed the search; they are not returned again ("more like them", not them)
    assert "Eixample Central Rooms" not in names and "Gràcia Garden Hotel" not in names
    for pick in picks:
        assert pick.price_per_night is not None and 61.6 <= pick.price_per_night <= 182.0
        assert pick.star_rating is not None and pick.star_rating >= 2
        assert pick.why.get("preference", 0.0) >= 0.0  # wanted-only never penalizes
    assert any(p.why.get("preference", 0.0) > 0.0 for p in picks)  # some actively favored


async def test_refine_exclude_list_suppresses_prior_pick() -> None:
    request = HotelRefineRequest(base=_BASE, exclude=["mock:bcn-011"])
    response = await refine(request, _settings())
    names = {p.name for picks in response.lenses.values() for p in picks}
    assert "Gothic Quiet Courtyard" not in names  # bcn-011


async def test_refine_id_round_trips_through_rediscovery() -> None:
    settings = _settings()
    first = await search(_BASE, settings)
    top = first.lenses[LensName.OVERALL_STANDOUTS][0]

    second = await refine(HotelRefineRequest(base=_BASE, exclude=[top.id]), settings)
    ids = {p.id for picks in second.lenses.values() for p in picks}
    # the echoed id survives a fresh stateless re-discovery and is excluded (statelessness proof)
    assert top.id not in ids


async def test_refine_without_feedback_matches_a_plain_search() -> None:
    settings = _settings()
    searched = await search(_BASE, settings)
    refined = await refine(HotelRefineRequest(base=_BASE), settings)

    assert refined.diagnostics.refined is True
    ids = lambda r: {p.id for picks in r.lenses.values() for p in picks}  # noqa: E731
    assert ids(refined) == ids(searched)  # no feedback => a re-search


def test_refine_sync_returns_structured_response_keyless() -> None:
    # Mirrors the orchestrator "Done" command: keyless (mock + heuristic), a structured envelope.
    request = HotelRefineRequest(
        base=_BASE,
        wanted=[HotelFeedback(id="mock:bcn-007", name="Diagonal Upscale Suites")],
        unwanted=[HotelFeedback(id="mock:bcn-008", name="Passeig Luxury Palace")],
    )
    response = refine_sync(request, _settings())

    assert response.agent_status in {"ok", "empty", "degraded"}
    assert response.diagnostics.refined is True
    names = {p.name for picks in response.lenses.values() for p in picks}
    assert "Passeig Luxury Palace" not in names  # unwanted excluded
