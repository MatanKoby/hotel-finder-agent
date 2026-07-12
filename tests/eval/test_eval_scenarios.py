"""Drive every evaluation scenario through ``search()`` and assert its result-quality properties.

Runs under ``make check`` on the offline mock provider + heuristic scorer, so it is deterministic
and free. Two layers of checks per scenario: the provider-independent contract invariants
(``metrics.check_invariants``, must be empty for all scenarios) and the scenario's own declared
``Expect`` (status, lenses filled, offers/prices/distances present, widening, over-budget fallback).
"""

from __future__ import annotations

import pytest
from metrics import evaluate
from scenarios import SCENARIOS, Scenario, eval_settings

from hotel_finder import search_sync
from hotel_finder.contracts import HotelSearchResponse

_IDS = [sc.name for sc in SCENARIOS]


def _run(scenario: Scenario) -> HotelSearchResponse:
    return search_sync(scenario.request, eval_settings())


def test_catalog_is_sane() -> None:
    assert SCENARIOS, "the scenario catalog is empty"
    assert len(_IDS) == len(set(_IDS)), "scenario names must be unique"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_no_invariant_violations(scenario: Scenario) -> None:
    """The contract guarantees hold for every scenario, whatever the request asks for."""
    response = _run(scenario)
    violations = evaluate(scenario.request, response, scenario.name).invariant_violations
    assert violations == [], f"{scenario.name}: {violations}"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_expectations(scenario: Scenario) -> None:
    """Each scenario's declared result-quality expectations are met."""
    expect = scenario.expect
    response = _run(scenario)
    picks = [pick for plist in response.lenses.values() for pick in plist]
    offers_total = sum(len(pick.offers) for pick in picks)

    if expect.status is not None:
        assert response.agent_status == expect.status

    populated = sum(1 for plist in response.lenses.values() if plist)
    assert populated >= expect.min_populated_lenses, (
        f"only {populated} lenses populated, wanted >= {expect.min_populated_lenses}"
    )

    if expect.expect_offers is True:
        assert offers_total > 0, "expected priced offers, got none"
        missing = [p.name for p in picks if p.price_per_night is not None and not p.offers]
        assert not missing, f"priced picks with no offer: {missing}"
    elif expect.expect_offers is False:
        assert offers_total == 0, "expected no offers"

    if expect.expect_widened is not None:
        assert response.diagnostics.widened is expect.expect_widened

    if expect.expect_over_budget is not None:
        over = sum(1 for p in picks for o in p.offers if o.over_budget)
        assert (over > 0) is expect.expect_over_budget, f"over_budget offers = {over}"

    if expect.expect_distance is True:
        located = [p for p in picks if p.coordinates is not None]
        assert located, "expected located picks to measure distance against"
        assert all(p.distance_to_desired_km is not None for p in located)

    if expect.warning_substr is not None:
        assert any(expect.warning_substr in w for w in response.warnings), (
            f"no warning contains {expect.warning_substr!r}; warnings={response.warnings}"
        )

    if expect.max_price_per_night is not None:
        offending = [
            (p.name, p.price_per_night)
            for p in picks
            if p.price_per_night is not None and p.price_per_night > expect.max_price_per_night
        ]
        assert not offending, f"picks above budget {expect.max_price_per_night}: {offending}"
