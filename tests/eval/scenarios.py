"""The evaluation scenario catalog: representative ``search()`` requests + what to expect.

Each :class:`Scenario` pairs a ``HotelSearchRequest`` with a declarative :class:`Expect` of the
result-quality properties that request should produce. The catalog is the shared source of truth for
both ``test_eval_scenarios.py`` (assertions, run under ``make check``) and ``report.py`` (metrics
baseline, run by hand) so the two never drift.

The offline baseline runs against the bundled **mock** provider + **heuristic** scorer, so the whole
set is deterministic, network-free, and free of charge. The scenario *definitions* are
provider-agnostic: point :func:`eval_settings` at ``liteapi`` + ``llm`` to replay the same requests
against live data. Assertions that pin exact dataset numbers live in the tests, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from hotel_finder.config import Settings
from hotel_finder.contracts import (
    Filters,
    HotelSearchRequest,
    Occupancy,
    Place,
    Stay,
)
from hotel_finder.models import GeoPoint

# Fixed dates keep every run identical. The mock provider ignores the query, so the concrete values
# only need to be a valid future-ish stay; nothing here depends on today's date.
_CHECK_IN = date(2026, 9, 1)
_CHECK_OUT = date(2026, 9, 4)  # 3 nights

# Plaça de Catalunya, the centre of the bundled Barcelona fixture city, for the geo scenario.
_BCN_CENTER = GeoPoint(lat=41.3874, lon=2.1686)


def _stay(**overrides: object) -> Stay:
    data: dict[str, object] = {"check_in": _CHECK_IN, "check_out": _CHECK_OUT}
    data.update(overrides)
    return Stay(**data)


def eval_settings() -> Settings:
    """Hermetic offline settings: mock provider + heuristic scorer, no ``.env``."""
    return Settings(_env_file=None, enabled_providers=["mock"], scorer="heuristic")


@dataclass(frozen=True)
class Expect:
    """Declarative result-quality expectations for one scenario (``None`` means "don't assert").

    These are the human-authored intent; the mechanical, provider-independent guarantees (score
    range, dedupe, status/warning coherence, offer sanity) live in ``metrics.check_invariants`` and
    are asserted for *every* scenario regardless of what is set here.
    """

    status: str | None = None  # exact agent_status: "ok" | "empty" | "degraded"
    min_populated_lenses: int = 0  # at least this many lenses come back non-empty
    expect_offers: bool | None = None  # True: priced picks carry offers; False: no offers at all
    expect_widened: bool | None = None  # whether bounded-agency widening should have fired
    expect_over_budget: bool | None = None  # whether any returned offer is flagged over_budget
    expect_distance: bool | None = None  # whether picks with coordinates carry distance_to_desired
    warning_substr: str | None = None  # a warning containing this substring must be present
    max_price_per_night: float | None = None  # every returned pick's price must be <= this


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    request: HotelSearchRequest
    expect: Expect = field(default_factory=Expect)


SCENARIOS: list[Scenario] = [
    Scenario(
        name="zone_default",
        description="Plain city zone search with a neighbourhood bias and a 3-night stay.",
        request=HotelSearchRequest(
            place=Place(country_code="ES", city="Barcelona", desired_area="El Born"),
            stay=_stay(),
            filters=Filters(min_guest_rating=8.0),
        ),
        expect=Expect(
            status="ok",
            min_populated_lenses=3,
            expect_offers=True,
            expect_widened=False,
            expect_over_budget=False,
        ),
    ),
    Scenario(
        name="budget_capped",
        description="A budget ceiling plenty of hotels satisfy: hard filter, no widening.",
        request=HotelSearchRequest(
            place=Place(country_code="ES", city="Barcelona"),
            stay=_stay(),
            filters=Filters(price_max=150),
        ),
        expect=Expect(
            status="ok",
            min_populated_lenses=2,
            expect_offers=True,
            expect_widened=False,
            expect_over_budget=False,
            max_price_per_night=150,
        ),
    ),
    Scenario(
        name="budget_too_low",
        description="Budget below the cheapest hotel: widening, over-budget fallback + warning.",
        request=HotelSearchRequest(
            place=Place(country_code="ES", city="Barcelona"),
            stay=_stay(),
            filters=Filters(price_max=40),
        ),
        expect=Expect(
            status="degraded",
            min_populated_lenses=1,
            expect_widened=True,
            expect_over_budget=True,
            warning_substr="no hotels within",
        ),
    ),
    Scenario(
        name="refundable_only_true",
        description="Restrict to refundable rates; the mock's rates are all refundable.",
        request=HotelSearchRequest(
            place=Place(country_code="ES", city="Barcelona"),
            stay=_stay(),
            filters=Filters(refundable=True),
        ),
        expect=Expect(status="ok", min_populated_lenses=3, expect_offers=True),
    ),
    Scenario(
        name="refundable_only_false",
        description="Restrict to non-refundable rates; the mock has none, so no offers.",
        request=HotelSearchRequest(
            place=Place(country_code="ES", city="Barcelona"),
            stay=_stay(),
            filters=Filters(refundable=False),
        ),
        # Picks still come back (content is there); they just have no priced offer to show.
        expect=Expect(status="ok", min_populated_lenses=3, expect_offers=False),
    ),
    Scenario(
        name="content_only_no_stay",
        description="No dates: content recommendations only, no live rates and so no offers.",
        request=HotelSearchRequest(
            place=Place(country_code="ES", city="Barcelona", desired_area="Gràcia"),
        ),
        expect=Expect(status="ok", min_populated_lenses=3, expect_offers=False),
    ),
    Scenario(
        name="high_bar_rating",
        description="A rating floor few hotels clear: quality bound held, area widening to fill.",
        request=HotelSearchRequest(
            place=Place(country_code="ES", city="Barcelona"),
            stay=_stay(),
            filters=Filters(min_guest_rating=9.5),
        ),
        expect=Expect(status="ok", min_populated_lenses=1, expect_widened=True),
    ),
    Scenario(
        name="geo_center_radius",
        description="Search around an explicit point: exact distances populated, radius filtering.",
        request=HotelSearchRequest(
            place=Place(center=_BCN_CENTER, radius_km=6.0),
            stay=_stay(rooms=[Occupancy(adults=2)]),
        ),
        expect=Expect(
            status="ok",
            min_populated_lenses=3,
            expect_offers=True,
            expect_distance=True,
        ),
    ),
]
