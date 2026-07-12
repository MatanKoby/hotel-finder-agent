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
- **`ANCHOR` intent** — resolve a named hotel → its band/area/rating, then find peers within
  that envelope. The field is already reserved on `HotelSearchRequest` (see `contract.md`).
- **Booking flow (LiteAPI prebook / book / retrieve / cancel).** LiteAPI supports it off the rate
  `offerId`, but M1 (and v1) is read-only recommendation. Noted for the future in
  `data-sources.md` → LiteAPI. Out of scope now.
- **The orchestration layer** above the three agents (still external).
- Optional: make `diagnostics.scorer` report the scorer that actually ran (vs configured) on LLM
  fallback (see `contract.md` → `Diagnostics`).
- Optional: richer per-lens rationales in `explain.py` (lens-aware phrasing).

## Open considerations to revisit

- The heuristic weightings/thresholds (`scoring.md`) and price-band cutoffs (`config.md`) are
  reasonable starting values, not tuned.
- Widening currently **drops** price bounds entirely on step 2; gentler relaxation (e.g. widen
  the band) is possible (see `pipeline.md` → Filter + widening).
- The mock `api.py` ignores the query and returns its whole fixture city (see `providers.md`).
