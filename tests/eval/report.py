"""Run the whole evaluation catalog and print a result-quality baseline table.

This is the by-hand companion to ``test_eval_scenarios.py``: same scenarios, same offline mock +
heuristic run, but instead of asserting it prints per-scenario metrics so a developer can *see* the
baseline and watch it move. Batch P2 tunes against these numbers.

    make eval
    uv run python tests/eval/report.py

Exits non-zero if any scenario breaks a contract invariant, so it can also gate CI. Point it at live
data by editing ``scenarios.eval_settings`` (LiteAPI + LLM) — the catalog is provider-agnostic.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python tests/eval/report.py` to import the sibling modules when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import ScenarioMetrics, evaluate  # noqa: E402
from scenarios import SCENARIOS, eval_settings  # noqa: E402

from hotel_finder import search_sync  # noqa: E402

_COLUMNS = "  {name:<22} {status:<8} {lenses:>5} {picks:>7} {price:>5} {offers:>6} {coord:>5} "
_COLUMNS += "{image:>5} {dist:>5} {ovb:>3} {wdn:>3} {warn:>4}"
_HEADER = _COLUMNS.format(
    name="scenario",
    status="status",
    lenses="lens",
    picks="picks",
    price="prc%",
    offers="off%",
    coord="crd%",
    image="img%",
    dist="dst%",
    ovb="ovb",
    wdn="wdn",
    warn="warn",
)


def _pct(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%" if whole else "-"


def _row(m: ScenarioMetrics) -> str:
    return _COLUMNS.format(
        name=m.name,
        status=m.status,
        lenses=f"{m.lenses_populated}/{m.lenses_total}",
        picks=f"{m.picks_total}/{m.picks_unique}",
        price=_pct(m.with_price, m.picks_total),
        offers=_pct(m.with_offers, m.picks_total) if m.stay_present else "-",
        coord=_pct(m.with_coords, m.picks_total),
        image=_pct(m.with_image, m.picks_total),
        dist=_pct(m.with_distance, m.picks_total),
        ovb=str(m.over_budget_offers),
        wdn="yes" if m.widened else "no",
        warn=str(m.warnings),
    )


def collect() -> list[ScenarioMetrics]:
    """Run every scenario offline and return its metrics, in catalog order."""
    settings = eval_settings()
    results: list[ScenarioMetrics] = []
    for scenario in SCENARIOS:
        response = search_sync(scenario.request, settings)
        results.append(evaluate(scenario.request, response, scenario.name))
    return results


def main() -> int:
    metrics = collect()
    print("hotel-finder evaluation baseline (offline mock provider + heuristic scorer)\n")
    print(_HEADER)
    print("  " + "-" * (len(_HEADER) - 2))
    for m in metrics:
        print(_row(m))

    print(
        "\nlegend: lens=populated/total  picks=total/unique  prc/off/crd/img/dst%=share of picks "
        "with a\n        price / offer / coordinates / image / distance  ovb=over-budget offers  "
        "wdn=widened  warn=#warnings"
    )

    violations = [(m.name, v) for m in metrics for v in m.invariant_violations]
    if violations:
        print(f"\nINVARIANT VIOLATIONS ({len(violations)}):")
        for name, problem in violations:
            print(f"  ! {name}: {problem}")
        return 1
    print(f"\nall {len(metrics)} scenarios pass the contract invariants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
