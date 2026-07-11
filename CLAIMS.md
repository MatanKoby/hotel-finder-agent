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

### Batch M1b — LiteAPI provider (real hotels, content, and prices)
- Owner: claude
- Started: 2026-07-11 14:31
- Finished: 2026-07-11 14:43
- Commit: 00247df

**What shipped.** A self-contained `providers/liteapi/` folder: `api.py` (async `httpx`
`LiteApiClient` for `GET data/hotels` discovery+content and `POST hotels/rates`, `X-API-Key`
header), `adapter.py` (maps a `data/hotels` item → `Hotel` per the `spec/data-sources.md` mapping
table: coords, `city`→area, `stars`→`star_rating`, guest `rating` kept 0-10, `reviewCount`,
`facilityIds`→`Amenity` via the shipped `facilities.json` id→name dict + `normalize_amenity`,
HTML `hotelDescription` stripped; and `hotels/rates` → the **cheapest refundable + cheapest
non-refundable** offer per hotel, `refundableTag` "RFN"→True/"NRFN"→False), and `provider.py`
(the two-call join; rates fetched only when `stay` is present). The registry moved to **provider
factories** (`Settings -> HotelProvider`) so real sources get credentials; the pipeline now calls
`get_providers(names, settings)`. `pipeline._offers_for` prefers provider-normalized offer dicts in
`hotel.raw["offers"]` (falls back to synthesizing from `price_per_night` for the mock), applying the
budget flag and `refundable` filter once. Added `LITEAPI_API_KEY`/`LITEAPI_BASE_URL`/
`LITEAPI_TIMEOUT` to `Settings`, `httpx` to deps, and `utils.strip_html`. LiteAPI is **disabled by
default** (`enabled_providers=["mock"]`), so CI stays offline.

**Verification.** `make check` green (ruff + mypy strict on 30 source files); pytest 47 passed
(+7 in `tests/test_liteapi.py`: adapter mapping from the recorded fixtures, cheapest-of-each-kind
offers, content-only, stubbed-client provider join, and a stubbed end-to-end pipeline run incl.
over-budget fallback and the refundable filter). Also **verified live** against the LiteAPI sandbox
key in `.env`: `search()` with `enabled_providers=["liteapi"]` returned 50 real Barcelona hotels
with real names, stars, 0-10 ratings, and EUR rates + refundable flags, `status=ok`.

**Deferred / notes.** `filters.property_types` narrowing is **not enforced** yet: LiteAPI gives an
integer `hotelTypeId` (stored in `raw`) but there is no recorded type-id→label dictionary to match
against (parallel to `facilities.json`); flag for the user — either record that dict or drop the
field. Rates use the retail `total`; `suggestedSellingPrice`/`rateId`/`offerId` are ignored (booking
deferred). No `.env` needed for the offline path; live use needs `LITEAPI_API_KEY`. Next: M1c
(place resolution / geocoding) and M1d (Nebius scoring), then M1e. `dev` remains local-only,
unpushed.

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
