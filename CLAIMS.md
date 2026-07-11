# Claims

Execution-state ledger, managed by coding agents. Records who is working on what and the recent
completion log. The user does not normally edit this. Procedures:
`specflow/procedures/claim-batch.md` and `specflow/procedures/finish-batch.md`.

Entry format:

```
### Batch N — <short title>
- Owner: <agent>
- Started: YYYY-MM-DD HH:MM        (UTC)
- Finished: YYYY-MM-DD HH:MM       (only in Completed)
- Commit: <short SHA>              (only in Completed)
- Handoff note: ...                (only when a mid-batch handoff occurred)
```

## In progress

<!-- One entry per actively claimed batch. -->

## Completed

<!-- Recent finishes, newest first. Older entries archived to specflow/history/CLAIMS_DONE.md. -->

### Batch M1a — Contract + the submodule search API
- Owner: claude
- Started: 2026-07-11 11:15
- Finished: 2026-07-11 14:31
- Commit: 518dd45

**What shipped.** Refactored `contracts.py` from the v1 `HotelQuery`/`Recommendations` to the
submodule surface in `spec/contract.md`: `HotelSearchRequest` (`Place`/`Occupancy`/`Stay`/`Filters`,
`extra="forbid"`, price/date validators) in, a `HotelSearchResponse` envelope
(`status` ok/empty/degraded + `warnings` + `resolved` + `lenses` + `meta`) out, plus `RateOffer`,
`ResolvedQuery`, and `Pick` gaining `offers`. `pipeline.py` now exposes `async search()` and a thin
`search_sync()`, resolves `Place` into `ResolvedQuery` (free-text geocoding stubbed → M1c), turns
provider failures into warnings (never fatal), derives read-only offers from `price_per_night` when
a `stay` is present (real LiteAPI rates → M1b), and implements the budget-too-low fallback
(over-budget offers flagged, `status=degraded`, price-floor warning). Introduced an internal
`context.py:SearchContext` so shortlist/scorers no longer depend on the public request shape.
Folded in the already-specced **guest-rating rescale to 0-10** (`models.py` bound, heuristic
`value` `rating/10` + gem `(rating-8)/2`, shortlist, and the mock Barcelona fixtures ×2), since the
LiteAPI adapter (M1b) targets a 0-10 `Hotel.rating`. Wired `min_star`/`min_guest_rating` into
`stages/filtering.py`. Top-level re-exports `search`/`search_sync` + request/response + sub-models +
`Settings`; `demo.py` updated to the new API (deleted in M1e).

**Verification.** `make check` green (ruff + mypy strict on 26 source files); pytest 40 passed
(was 26) including new `tests/test_contract.py` (validation raises at construction) and envelope /
offers / status / `search_sync` coverage in `tests/test_pipeline.py`. `from hotel_finder import
search` and `python -m hotel_finder.demo` both run offline with the heuristic scorer.

**Deferred / notes.** No mandatory `.env`, `py.typed`, and the `examples/orchestrator_sim.py` proof
are M1e. Real prices/refundability come from M1b (M1a synthesizes one refundable offer per hotel
from the provider price). `over_budget` is computed per-night (consistent with the existing
price filter); `spec/contract.md` phrases it as "total exceeds price_max" — flag for the user if a
total-vs-total budget is wanted. `dev` branch is local-only and unpushed (HTTPS remote, no
non-interactive auth).
