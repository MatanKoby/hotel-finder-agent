# Roadmap: status, out-of-scope, next steps, open questions

The forward-looking and historical view. The current intended design lives in the other spec
files; this one holds status, deferred work, and decisions still to revisit. Active work derived
from this file is tracked as batches in `BUILD_QUEUE.md`.

## Status (v1)

**Done:** full vertical slice — contract + mock provider + all stages + heuristic & LLM scorers
+ 3 lenses + demo; 26 offline tests; ruff + mypy clean. Git initialized. Commit on request.

## Milestone 1: submodule-ready with real results (in planning)

**Goal.** Deliver hotel-finder as an importable **git submodule** the orchestrator can integrate as
its **first example**. With a LiteAPI key and Nebius LLM access configured (env, or a `Settings`
injected by the caller), the orchestrator builds a `HotelSearchRequest`, calls `search()`, and gets
a `HotelSearchResponse` with **real** hotels and accommodations nearby (real names, descriptions,
coordinates, and prices), across the three lenses, scored by the Nebius LLM. This proves the
pipeline end to end against a live source, and pulls "real provider folders" and "real geocoding"
forward into this milestone. A minimal `examples/orchestrator_sim.py` exercises the import →
`search()` → envelope path locally; **there is no interactive CLI**. The Definition of Done and the
M1 batch breakdown (M1a–M1e) live in `BUILD_QUEUE.md`.

**This repo is a git submodule of an orchestrator agent.** The interface is the typed `search()`
API (async) plus a thin sync `search_sync()`: the orchestrator imports `HotelSearchRequest` from
this submodule, validates its input against that shared model, and calls `search()` to get a
`HotelSearchResponse` envelope (see `contract.md`). **No `.env` is required when imported**: config
comes from the caller's environment or an injected `Settings`.

**Approved (planning session 2026-07-10):**

- **Nebius is the LLM provider only**, not a data source. In M1 it does scoring and enrichment,
  reached behind the `HotelScorer` interface (see `scoring.md`, `config.md`).
- **Two LLM run modes** (mirroring the sibling flight agent). **Eval/testing** inside this repo
  uses a Nebius **Token Factory** model via an API key (uncapped model choice). The
  **orchestrator** context uses a **shared Nebius Serverless AI endpoint** (Ollama REST, bearer
  token, no API key, single served model auto-discovered). This repo contacts both itself; it is
  never handed an endpoint by the orchestrator. See `scoring.md`, `config.md`.
- **Results must be real.** No LLM-fabricated listings in M1.
- **At least one working real, free data API** is required for M1. The design should support
  **multiple** free hotel/accommodation sources over time; the provider architecture in
  `providers.md` already allows adding sources without core changes.
- **No interactive CLI.** hotel-finder is used as a library/submodule, not a user-facing CLI. The
  `search()` path is exercised locally by a minimal `examples/orchestrator_sim.py` and by tests
  (see `BUILD_QUEUE.md`). It still spans hotels and broader accommodation types (hostels,
  guesthouses, apartments, and similar).
- **LLM web search as a backup source** is wanted, but secondary to landing the first real API
  (chat completions do not browse, so it needs a separate search tool/API). Likely a follow-up,
  not part of the first working slice.

**Data source (decided 2026-07-10):** **LiteAPI (Nuitée)** is the M1 source. It is the one free
provider that natively returns location + description + price in a single vendor (free sandbox
key, no card). This also resolves the earlier "price handling" question for M1: LiteAPI carries
real rates, so no LLM-estimated band or separate price API is needed for the first slice. Full
comparison of every provider evaluated (OSM, Amadeus, Xotelo, Geoapify, OpenTripMap, Makcorps,
Airbnb), the live-test findings, and the fallback combine strategy live in **`data-sources.md`**.

**Provider iteration (deferred past M1):** running **multiple** sources (an OSM breadth layer, an
independent price cross-check, richer descriptions, LLM web-search backup) is future work,
catalogued in `data-sources.md` → Future direction and to be broken into batches after M1 lands.

## Out of scope for v1 / candidate next steps

- **Real provider folders** (e.g. Amadeus / Google Places adapters; a scraper), each one
  `api.py` + `adapter.py` + registry line (see `providers.md`, `dev-guide.md`). **Now pulled
  into Milestone 1 above.**
- **Real geocoding**: turn `desired_area`/`location` strings into a `center` GeoPoint so
  distance filtering and ranking are exact rather than name-match (touches `pipeline.md` filter
  and shortlist stages). **Now pulled into Milestone 1 above** (via free Nominatim).
- ~~**`ANCHOR` intent**~~ — **done (P3):** resolve a named hotel to a peer envelope (proximity +
  price window + star/rating floors), exclude it, and return peers; broad-zone fallback when the
  anchor is unresolved. See `pipeline.md` → Anchor intent and `contract.md` → intent/anchor_hotel.
- **Booking flow (LiteAPI prebook / book / retrieve / cancel).** LiteAPI supports it off the rate
  `offerId`, but M1 (and v1) is read-only recommendation. Noted for the future in
  `data-sources.md` → LiteAPI. Out of scope now.
- **The orchestration layer** above the three agents (still external).
- Optional: make `diagnostics.scorer` report the scorer that actually ran (vs configured) on LLM
  fallback (see `contract.md` → `Diagnostics`).
- Optional: richer per-lens rationales in `explain.py` (lens-aware phrasing).

## Baseline findings (P1/P6 live eval, 2026-07-13)

Concrete result-quality gaps observed running the `tests/eval/` catalog live against real LiteAPI
Barcelona hotels + Nebius Token Factory (`Qwen/Qwen3-32B`, thinking off). These were the inputs to
**Batch P2** (`BUILD_QUEUE.md`); re-measure any fix with `make eval`. **Items 1–5 are addressed by
Batch P2** (see `specflow/history/BUILD_QUEUE_DONE.md`); item 6 remains open.

1. ~~**Content-only empties `stratified_best`.**~~ **Fixed (P2):** a star-tier fallback fills the
   lens when no candidate has a price band (verified live: content-only now fills stratified_best) —
   `stages/lenses.py`, `pipeline.md` → Lenses.
2. ~~**The neighbourhood bias barely ranks.**~~ **Fixed (P2):** `desired_area` geocodes to a ranking
   point (a soft bias, not a hard filter), and the heuristic name-only `location` is now graded, not
   a flat match/non-match — `pipeline.py` → Resolve, `scoring.md` → heuristic location.
3. ~~**Distance measured only for explicit-centre requests.**~~ **Fixed (P2):** the geocoded desired
   point populates `distance_to_desired_km` for area-string scenarios too (verified: `dst%` 100% for
   the zone/content scenarios) — `pipeline.py`.
4. ~~**The LLM `location` subscore is ungrounded.**~~ **Fixed (P2):** `_hotel_payload` now feeds
   `coordinates` + `distance_to_desired_km` + `in_desired_area` and the prompt scores from them
   (verified live: `location` tracks distance, no longer `1.00` for all) — `scoring/llm.py`.
5. ~~**Rationales can self-contradict; gems thin.**~~ **Partly fixed (P2):** the "few reviews" gem
   phrasing is gated on a known-low `review_count`, the LLM is told not to gem-label well-reviewed
   hotels, and rationales are lens-aware — `scoring/heuristic.py`, `stages/explain.py`, `scoring.md`.
   The **thinness** is largely inherent: a popular city's hotels are well-reviewed, so few clear the
   "under-the-radar" bar; the bar stays conservative by design rather than dilute the concept.
6. **Only structure is asserted, not semantics** (open). The harness proves results are well-formed,
   not that the ranking/rationales are *good* — a future eval extension could add quality metrics.

**Operational (not P2):** the LLM path has unstable latency — `Qwen3-32B` intermittently times out
even with thinking off (~1 min/scenario), degrading that scenario to the heuristic (visible in the
`make eval` `scorer` column). Options: a longer/adaptive `LLM_TIMEOUT`, a smaller `shortlist_size`
to the LLM, or running scenarios in parallel. Track separately from result quality.

## Open considerations to revisit

- The heuristic weightings/thresholds (`scoring.md`) and price-band cutoffs (`config.md`) are
  reasonable starting values, still **not tuned** — safe tuning wants the semantic eval of finding 6
  (a ground truth to measure against) rather than blind number changes.
- ~~Widening drops price bounds entirely~~ — **addressed (P2):** widening is now gentle (middle
  steps widen the band by `widen_price_factor`, only the final step drops the bounds); see
  `pipeline.md` → Filter + widening.
- The mock `api.py` ignores the query and returns its whole fixture city (see `providers.md`).
