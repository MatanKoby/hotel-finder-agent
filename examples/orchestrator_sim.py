"""Minimal orchestrator simulator: drive hotel-finder's public API exactly as the orchestrator will.

hotel-finder is a library/submodule with **no interactive CLI**. This script stands in for the
orchestrator: it builds a `HotelSearchRequest` from the exported Pydantic models, calls the async
`search()` entry point (the blocking `search_sync()` wrapper is shown too), and pretty-prints the
`HotelSearchResponse` envelope (status, warnings, resolved query, lenses, priced offers).

Run it:

    make run
    uv run python examples/orchestrator_sim.py

With no configuration it uses the bundled **mock** provider + the **heuristic** scorer, fully
offline and free. Point it at real services via the environment (see `.env.example`):

    ENABLED_PROVIDERS=liteapi LITEAPI_API_KEY=sand_... SCORER=llm LLM_API_KEY=...  make run
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from hotel_finder import (
    Filters,
    HotelSearchRequest,
    HotelSearchResponse,
    LensName,
    Place,
    Settings,
    Stay,
    search,
    search_sync,
)

_LENS_TITLES = {
    LensName.STRATIFIED_BEST: "Best in each price tier",
    LensName.OVERALL_STANDOUTS: "Overall standouts",
    LensName.HIDDEN_GEMS: "Hidden gems",
}


def build_request() -> HotelSearchRequest:
    """The kind of request the orchestrator would construct (and validate) on its own side."""
    check_in = date.today() + timedelta(days=30)
    return HotelSearchRequest(
        place=Place(country_code="ES", city="Barcelona", desired_area="El Born"),
        stay=Stay(check_in=check_in, check_out=check_in + timedelta(days=3)),
        filters=Filters(min_guest_rating=8.0),
        picks_per_lens=3,
    )


def run(settings: Settings | None = None) -> HotelSearchResponse:
    """Build the request and call the blocking wrapper. Used by `main()` and the smoke test."""
    return search_sync(build_request(), settings)


def main() -> None:
    settings = Settings()  # reads the environment / .env; safe offline defaults
    print(
        f"providers={settings.enabled_providers}  scorer={settings.scorer}  "
        f"llm_backend={settings.llm_backend}"
    )

    request = build_request()
    # The orchestrator awaits the async entry point:
    response = asyncio.run(search(request, settings))
    # The same result is available synchronously via `search_sync(request, settings)`.
    _render(response)


def _render(response: HotelSearchResponse) -> None:
    diag = response.diagnostics
    resolved = response.resolved
    print(
        f"\nstatus={response.agent_status}  scorer={diag.scorer}  found={diag.candidates_found}  "
        f"after_filter={diag.candidates_after_filter}  shortlisted={diag.shortlisted}  "
        f"widened={diag.widened}"
    )
    where = resolved.city or (f"{resolved.center.lat:.3f},{resolved.center.lon:.3f}"
                              if resolved.center else "?")
    dates = f"{resolved.check_in} → {resolved.check_out}" if resolved.check_in else "no dates"
    area = f"  ({resolved.area})" if resolved.area else ""
    print(f"resolved: {where}{area}  |  {dates}  |  {resolved.currency or ''}")
    for warning in response.warnings:
        print(f"  ! {warning}")

    for lens, picks in response.lenses.items():
        print(f"\n== {_LENS_TITLES.get(lens, lens.value)} ==")
        if not picks:
            print("  (none)")
            continue
        for pick in picks:
            where = pick.area or "?"
            stars = f"{pick.star_rating}*" if pick.star_rating else "?*"
            rating = f"r={pick.rating}" if pick.rating is not None else ""
            print(f"  • {pick.name}  [{where}, {stars} {rating}]  score={pick.score:.2f}")
            for offer in pick.offers:
                flags = "refundable" if offer.refundable else "non-refundable"
                if offer.over_budget:
                    flags += ", OVER BUDGET"
                per_night = f" ({offer.per_night:.0f}/night)" if offer.per_night else ""
                label = offer.board or flags
                print(f"      {offer.currency} {offer.total:.0f}{per_night} — {label}")
            if pick.rationale:
                print(f"      {pick.rationale}")


if __name__ == "__main__":
    main()
