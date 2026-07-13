"""Result-quality metrics and provider-independent invariants over a ``HotelSearchResponse``.

Two pure entry points, both taking the ``(request, response)`` pair:

* :func:`check_invariants` returns the list of contract guarantees the response **violated** (empty
  list == healthy). These hold for *any* request against *any* provider, so both the tests and the
  report treat a non-empty list as a hard failure.
* :func:`evaluate` returns a :class:`ScenarioMetrics` of countable quality signals (lenses filled,
  prices/offers/coords present, over-budget offers, widening, ...) — the numbers ``report.py``
  prints as the baseline that Batch P2 tunes against.

Kept free of pytest so ``report.py`` can reuse it outside a test run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hotel_finder.contracts import (
    HotelSearchRequest,
    HotelSearchResponse,
    LensName,
    Pick,
    RateOffer,
)
from hotel_finder.models import PriceBand

_EPS = 1e-6
# stratified_best emits at most one pick per price band; the others are capped at picks_per_lens.
_MAX_BANDS = len(PriceBand)


def _offer_basis(offer: RateOffer) -> float:
    """The per-night amount a budget is compared against (falls back to the stay total)."""
    return offer.per_night if offer.per_night is not None else offer.total


def check_invariants(request: HotelSearchRequest, response: HotelSearchResponse) -> list[str]:
    """Return every contract guarantee ``response`` breaks for ``request`` (empty == all held)."""
    problems: list[str] = []
    lenses = response.lenses
    all_picks: list[tuple[LensName, Pick]] = [
        (lens, pick) for lens, picks in lenses.items() for pick in picks
    ]
    has_picks = bool(all_picks)

    # --- envelope: id echo + status/warning/picks coherence (mirrors pipeline._status) ---
    if response.request_id != request.request_id:
        problems.append(
            f"request_id not echoed ({response.request_id!r} != {request.request_id!r})"
        )
    if not has_picks:
        expected_status = "empty"
    elif response.warnings:
        expected_status = "degraded"
    else:
        expected_status = "ok"
    if response.agent_status != expected_status:
        problems.append(
            f"agent_status={response.agent_status!r} but picks/warnings imply {expected_status!r}"
        )

    # --- per-lens: score range, count caps, and no dup identity within a projection ---
    for lens, picks in lenses.items():
        cap = _MAX_BANDS if lens is LensName.STRATIFIED_BEST else request.picks_per_lens
        if len(picks) > cap:
            problems.append(f"lens {lens.value} returned {len(picks)} picks (cap {cap})")
        names = [p.name for p in picks]
        if len(names) != len(set(names)):
            problems.append(f"lens {lens.value} has duplicate hotels: {names}")
        for pick in picks:
            if not (0.0 <= pick.score <= 1.0):
                problems.append(f"{pick.name}: score {pick.score} out of [0,1]")

    # --- one hotel scores the same in every lens it appears in (lenses select, not re-scale) ---
    seen_score: dict[str, float] = {}
    for _lens, pick in all_picks:
        prior = seen_score.get(pick.name)
        if prior is not None and abs(prior - pick.score) > _EPS:
            problems.append(f"{pick.name}: score differs across lenses ({prior} vs {pick.score})")
        seen_score.setdefault(pick.name, pick.score)

    # --- offers: currency, per-night <= total, over_budget/refundable honoured ---
    stay = request.stay
    price_max = request.filters.price_max
    want_refundable = request.filters.refundable
    for _lens, pick in all_picks:
        if stay is None and pick.offers:
            problems.append(f"{pick.name}: offers present without a stay")
        for offer in pick.offers:
            if stay is not None and offer.currency != stay.currency:
                problems.append(
                    f"{pick.name}: offer currency {offer.currency} != stay {stay.currency}"
                )
            if offer.per_night is not None and offer.per_night > offer.total + _EPS:
                problems.append(f"{pick.name}: per_night {offer.per_night} > total {offer.total}")
            if offer.over_budget and not (
                price_max is not None and _offer_basis(offer) > price_max + _EPS
            ):
                problems.append(
                    f"{pick.name}: offer flagged over_budget without exceeding price_max"
                )
            if want_refundable is not None and offer.refundable != want_refundable:
                problems.append(
                    f"{pick.name}: offer refundable={offer.refundable} violates filter "
                    f"refundable={want_refundable}"
                )

    # --- resolved echoes the stay (and only when there is one) ---
    resolved = response.resolved
    if stay is not None:
        if resolved.check_in != stay.check_in or resolved.check_out != stay.check_out:
            problems.append("resolved dates do not echo the stay")
        if resolved.currency != stay.currency:
            problems.append(f"resolved currency {resolved.currency} != stay {stay.currency}")
    elif resolved.check_in is not None or resolved.check_out is not None:
        problems.append("resolved carries dates for a content-only (no stay) request")

    # --- an explicit search centre yields exact distances for every located pick ---
    if request.place.center is not None:
        for _lens, pick in all_picks:
            if pick.coordinates is not None and pick.distance_to_desired_km is None:
                problems.append(
                    f"{pick.name}: distance_to_desired_km missing despite a search centre"
                )

    return problems


@dataclass(frozen=True)
class ScenarioMetrics:
    """Countable quality signals for one scenario run. Percentages are derived in the report."""

    name: str
    status: str
    scorer: str  # the scorer that actually ran (heuristic on LLM fallback)
    stay_present: bool
    lenses_total: int
    lenses_populated: int
    picks_total: int
    picks_unique: int
    with_price: int
    with_offers: int
    with_coords: int
    with_description: int
    with_image: int
    with_distance: int
    offers_total: int
    over_budget_offers: int
    widened: bool
    candidates_found: int
    candidates_after_filter: int
    shortlisted: int
    warnings: int
    invariant_violations: list[str] = field(default_factory=list)


def evaluate(
    request: HotelSearchRequest, response: HotelSearchResponse, name: str
) -> ScenarioMetrics:
    """Compute :class:`ScenarioMetrics` for one ``(request, response)`` run under label ``name``."""
    lenses = response.lenses
    picks = [pick for plist in lenses.values() for pick in plist]
    offers = [offer for pick in picks for offer in pick.offers]
    diag = response.diagnostics

    return ScenarioMetrics(
        name=name,
        status=response.agent_status,
        scorer=diag.scorer,
        stay_present=request.stay is not None,
        lenses_total=len(lenses),
        lenses_populated=sum(1 for plist in lenses.values() if plist),
        picks_total=len(picks),
        picks_unique=len({pick.name for pick in picks}),
        with_price=sum(1 for pick in picks if pick.price_per_night is not None),
        with_offers=sum(1 for pick in picks if pick.offers),
        with_coords=sum(1 for pick in picks if pick.coordinates is not None),
        with_description=sum(1 for pick in picks if pick.description),
        with_image=sum(1 for pick in picks if pick.image_url),
        with_distance=sum(1 for pick in picks if pick.distance_to_desired_km is not None),
        offers_total=len(offers),
        over_budget_offers=sum(1 for offer in offers if offer.over_budget),
        widened=diag.widened,
        candidates_found=diag.candidates_found,
        candidates_after_filter=diag.candidates_after_filter,
        shortlisted=diag.shortlisted,
        warnings=len(response.warnings),
        invariant_violations=check_invariants(request, response),
    )
