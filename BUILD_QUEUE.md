# Build Queue

Reference spec: [`spec/`](spec/README.md) (start at `spec/roadmap.md` → Milestone 1, and
`spec/contract.md`, `spec/data-sources.md`).
Agent work tracking: `CLAIMS.md` (managed by coding agents)
Completed history: [`specflow/history/BUILD_QUEUE_DONE.md`](specflow/history/BUILD_QUEUE_DONE.md) — one-paragraph summaries of shipped batches.

## How this works

- This file lists only **un-done batches**, in full. Completed batches collapse to summaries
  in `specflow/history/BUILD_QUEUE_DONE.md` (git log + `specflow/history/CLAIMS_DONE.md` hold the implementation history).
- Dependencies are listed where they exist — the agent decides execution order.
- Agents claim and track completion in `CLAIMS.md`. **No Owner / Started / Status ever goes in
  this file** — that's execution state, and it lives in `CLAIMS.md` only.
- Batches are designed so two agents can work different batches at once without file conflicts.
- See `specflow/procedures/claim-batch.md` before claiming.

---

## Milestone 1 — Definition of Done

M1 delivers hotel-finder as an importable **git submodule** the orchestrator can integrate as its
**first example**. With a **LiteAPI key** and **Nebius LLM access** configured (env, or a `Settings`
injected by the caller), the orchestrator builds a `HotelSearchRequest`, calls **`search()`** (or
the sync `search_sync()`), and gets a `HotelSearchResponse` with **real** hotels and accommodations
nearby (real names, descriptions, coordinates, and **prices** from LiteAPI), across the **three
lenses**, **scored by the Nebius LLM** (heuristic fallback on failure). **No `.env` is required when
imported; no mock data in the live path; no crashes** (data problems become `warnings` + `status`,
never exceptions). A minimal `examples/orchestrator_sim.py` proves the import → `search()` →
envelope path locally. **There is no interactive CLI** (verification is via the example + tests).

M1 is the set of batches **M1a–M1e** below. The v1 vertical slice (mock provider, pipeline,
scorers, lenses, 26 tests) is already done (see `spec/roadmap.md` → Status). Post-M1 batches
(testing, evaluation, quality) follow.

> **Pick-order pointer for "continue".** After a context clear, **ask** which un-done batch to
> claim rather than guessing. **M1a is the foundation** (the contract everything else builds on);
> M1b/M1c/M1d follow it in parallel; **M1e (integration surface + example) integrates last**.

---

## Batch M1a — Contract + the submodule search API

**Milestone 1. Foundation** for every other M1 batch. Ready.

**Depends on:** none.

**Goal.** Refactor `contracts.py` from the v1 `HotelQuery` / `Recommendations` to the submodule
API in `spec/contract.md`: a validated `HotelSearchRequest` in, a `HotelSearchResponse` envelope
out, exported so an orchestrator can validate input on its own side before calling.

### Deliverables
- Request models: `Place` (structured `country_code`+`city` / `center`+`radius_km`, plus a
  `text` geocode fallback and `desired_area`), `Occupancy`, `Stay` (optional), `Filters`
  (incl. `refundable: bool | None`), `HotelSearchRequest`. Validators for price and date ranges;
  `extra="forbid"`.
- Response models: `RateOffer` (total/currency/per_night/board/refundable/over_budget, no booking
  token), `ResolvedQuery`, `Pick` (adds `offers: list[RateOffer]`), `HotelSearchResponse`
  (`status` ok/empty/degraded + `warnings`, never raises for a data outcome). The budget-and-offers
  rule from `spec/contract.md`.
- Entry points: `async def search(request, settings=None) -> HotelSearchResponse` and a thin sync
  `search_sync(request, settings=None)`. `settings=None` reads env; a caller may inject `Settings`.
  Re-export `search`, `search_sync`, `HotelSearchRequest`, `HotelSearchResponse` (and sub-models)
  from `hotel_finder/__init__.py`.
- Pipeline produces the envelope (populates `status`, `warnings`, `resolved`) instead of raising
  on empty/degraded outcomes.

### Files this batch creates/edits
- `src/hotel_finder/contracts.py` (rewrite), `src/hotel_finder/__init__.py` (exports),
  `src/hotel_finder/pipeline.py` (build envelope; map `Place`/`Stay`; `search_sync`),
  `stages/explain.py` (`offers`), `tests/` (validation raises at construction; envelope
  status/warnings; content-only when `stay` omitted).

### Does NOT touch
- Scoring math; the LiteAPI provider (M1b); the geocoding impl (M1c) — the `text` fallback can be
  a stub here.

### Verification
- `make check` green; a `HotelSearchRequest` built from a mapping validates and a malformed one
  raises `ValidationError` at construction; `search()`/`search_sync()` return a
  `HotelSearchResponse` envelope.

---

## Batch M1b — LiteAPI provider (real hotels, content, and prices)

**Milestone 1.** The one real, free data source (`spec/data-sources.md` → LiteAPI, verified). Ready.

**Depends on:** M1a (for the `RateOffer` / `Hotel` shapes the adapter targets).

**Goal.** Add LiteAPI as a self-contained provider folder that returns **real** lodging with
location, description, and price, proving the provider architecture end to end against a live
source (`spec/providers.md`, `spec/dev-guide.md` → Add a data source).

### Deliverables
- `providers/liteapi/api.py`: `data/hotels` discovery (by `country_code`+`city` or
  `center`+`radius`) for content, then `POST hotels/rates` with the returned `hotelIds` for
  prices (only when `stay` is present). Sends `X-API-Key` from `LITEAPI_API_KEY`.
- `providers/liteapi/adapter.py`: normalize LiteAPI payloads to `Hotel` (name, coords, address,
  description, `stars`→`star_rating`, guest `rating` kept **0-10**, `review_count`, `facilityIds`
  mapped onto `Amenity`), and per hotel the **cheapest refundable + cheapest non-refundable** rate
  to `RateOffer`(s) (total/currency/per_night/board/refundable/over_budget). All lodging types by
  default; `filters.property_types` narrows.
- Registered in `providers/registry.py`; runs when `liteapi` is in `enabled_providers`; upstream
  errors are caught and surfaced as `warnings`, never fatal.
- Offline test from a **recorded** LiteAPI payload (no network in CI); secrets via `.env` only.

### Files this batch creates/edits
- `src/hotel_finder/providers/liteapi/` (new), `providers/registry.py`, `config.py`
  (`LITEAPI_API_KEY`, base URL — additive), `.env.example`, `tests/` (recorded-payload fixture).

### Does NOT touch
- The mock provider, pipeline stages, scoring math.

### Verification
- `make check` green with `liteapi` disabled by default; an integration test drives the adapter
  from a recorded payload and yields valid `Hotel`s with a `RateOffer`.

---

## Batch M1c — Place resolution (structured passthrough + text geocoding)

**Milestone 1.** Turns `Place` into what LiteAPI and distance ranking need. Ready.

**Depends on:** M1a (defines `Place`). Pairs with M1b.

**Goal.** Resolve `Place`: use `country_code`+`city` or `center` directly when given; when only
`text` is given, geocode it (LiteAPI's place lookup first, else free Nominatim) into
`country_code`+`city` and/or a `center` GeoPoint. Record what was resolved in `ResolvedQuery`.
Graceful, non-fatal fallback when geocoding fails (warn, proceed with what is known).

### Deliverables
- A geocoder helper behind an interface (offline test double), free backend, rate-limit aware
  (`User-Agent` header for Nominatim, see `spec/data-sources.md`).
- Pipeline resolves `Place` before provider dispatch and fills `resolved` on the response; a
  geocode failure adds a `warning` and does not crash.

### Files this batch creates/edits
- `src/hotel_finder/utils/geocode.py` (new), `src/hotel_finder/pipeline.py` (resolve step),
  `config.py` (geocoder endpoint — additive), `tests/` (offline geocoder double).

### Does NOT touch
- Scoring math, provider adapters.

### Verification
- `make check` green; a request with only `place.text` resolves to a `center`/city in a test
  using the double, and a forced geocode failure yields a warning, not an exception.

---

## Batch M1d — Nebius LLM scoring (two transports) + effective-scorer reporting

**Milestone 1.** Makes "scored by the Nebius LLM, heuristic fallback" real for **both run modes**. Ready.

**Depends on:** M1a (envelope `warnings` / `meta`).

**Goal.** Give `LLMScorer` two backends behind the `HotelScorer` interface (`spec/scoring.md`,
`spec/config.md`), both contacted by this repo, and make fallback observable.

### Deliverables
- **Backend A (OpenAI-compatible):** the `openai` SDK against `llm_base_url` + `llm_api_key` +
  `llm_model` (eval/testing → Nebius Token Factory). Existing path, kept.
- **Backend B (serverless endpoint):** a thin Ollama-REST client (`POST {url}/api/chat`, bearer
  `nebius_endpoint_token`), the single served model auto-discovered via `GET {url}/api/tags`,
  liveness probe + brief cold-start retry (orchestrator → shared Nebius endpoint, no API key).
- Backend selected by `llm_backend` / presence of env vars; both parse into the same
  `{"scores":[...]}` shape with one repair retry.
- On any fallback (no LLM configured, unreachable, error, omitted ids), `meta.scorer` reads
  `heuristic` and a `warning` records it; a successful LLM run reads `llm`.

### Files this batch creates/edits
- `src/hotel_finder/scoring/llm.py` (two backends), maybe `scoring/nebius_endpoint.py` (the thin
  endpoint client), `scoring/base.py` (effective scorer), `src/hotel_finder/pipeline.py`
  (`meta.scorer` + fallback warning), `config.py` (endpoint vars, additive), `.env.example`,
  `tests/` (stubbed clients for both backends; forced fallback reports `heuristic` + a warning).

### Does NOT touch
- Scoring math / weightings, provider adapters.

### Verification
- `make check` green with stubbed LLM clients; forced fallback reports `scorer=heuristic` + a
  warning; each backend parses a stubbed success into scores.

---

## Batch M1e — Integration surface + minimal orchestrator example

**Milestone 1. This is what makes M1 "submodule-ready."** Integrates M1a–M1d into an importable,
callable library with a runnable example. Ready.

**Depends on:** M1a (the API); consumes M1b/M1c/M1d for real data + scoring.

**Goal.** Make hotel-finder cleanly importable and usable as a git submodule, and prove it with a
**minimal** example that drives `search()` exactly as the orchestrator will. This is a usage proof,
**not** an evaluation harness (systematic eval is post-M1).

### Deliverables
- **Import surface:** finalize top-level exports (`search`, `search_sync`, `HotelSearchRequest`,
  `HotelSearchResponse`, sub-models, `Settings`); ship `py.typed`; `pip install -e .` works and
  `from hotel_finder import search` succeeds in a fresh env.
- **No mandatory `.env`:** `Settings` has safe defaults; config comes from the caller's environment
  or an injected `Settings`. Importing the package touches no network and needs no keys.
- **`examples/orchestrator_sim.py`:** builds a `HotelSearchRequest` via the exported model, calls
  `search()` (and shows `search_sync()`), and pretty-prints the `HotelSearchResponse` (status,
  warnings, lenses, offers). Live LiteAPI + Nebius when keyed; heuristic + warnings without.
- **Integration docs:** a short "use as a submodule" section in `README.md` (how the orchestrator
  adds the submodule and calls `search`); update `dev-guide.md`; `make run` runs the example;
  remove the obsolete `src/hotel_finder/demo.py`.

### Files this batch creates/edits
- `examples/orchestrator_sim.py` (new), `src/hotel_finder/__init__.py` (finalize exports),
  `pyproject.toml` (packaging, if needed), `README.md`, `Makefile` (`run` target), delete
  `src/hotel_finder/demo.py`, `tests/` (import/export smoke test; stubbed-provider sim run).

### Does NOT touch
- Provider internals, scoring math, the contract shape.

### Verification
- `make check` green; in a fresh venv `pip install -e .` then `from hotel_finder import search,
  HotelSearchRequest` works; `make run` prints a `HotelSearchResponse` envelope.

---

## Post-M1 batches (testing, evaluation, quality)

Out of scope for M1; unblock after it lands. M1 ships the capability; these make it work *well*.

### Batch P1 — Evaluation harness and test scenarios

**Depends on:** M1e. **Goal.** Start testing it actually works properly: representative scenarios
(cities, budgets, `refundable` variants, over-budget fallback, content-only) driven through
`search()` via the orchestrator wrapper, with quality assertions/metrics (lenses populated, prices
present, dedupe sane, `status`/`warnings` correct). Establishes the baseline for improving results.
Lands under `tests/eval/` (or `examples/eval/`).

### Batch P2 — Result-quality improvements

**Depends on:** P1 (a baseline to measure against). **Goal.** Improve results: lens-aware
rationales in `stages/explain.py` (a hotel under `hidden_gems` reads differently from
`stratified_best`), and tune the reasonable-but-untuned defaults from `spec/roadmap.md` → Open
considerations (heuristic weightings `spec/scoring.md`, price-band cutoffs `spec/config.md`,
gentler filter widening `spec/pipeline.md`).

### Batch P3 — `ANCHOR` intent (peers of a named hotel)

**Depends on:** M1b. **Open scope** → `spec-edit` first. **Goal.** Implement the reserved `anchor`
intent: resolve `anchor_hotel` to a band/area/rating envelope, then find peers within it
(`spec/contract.md` → `Intent`, `spec/roadmap.md`). Edits `pipeline.py` (intent branch), maybe
`stages/anchor.py`, `tests/`. `zone` behavior unchanged.

### Batch P4 — Additional data sources / multi-source blend

**Depends on:** M1b. **Open scope** → `spec-edit` first. **Goal.** Add further sources from
`spec/data-sources.md` → Future direction: an OSM breadth/fallback layer, an independent price
cross-check (Amadeus test / Xotelo `/rates`), or OpenTripMap/LLM descriptions. Each is a provider
folder per `spec/providers.md`; cross-source dedupe stays in the pipeline.

### Batch P5 — LLM web-search backup source

**Depends on:** M1b. **Open scope** → `spec-edit` first. **Goal.** The deferred backup from
`spec/roadmap.md` (M1 → web search is secondary): a separate search tool/API feeding the pipeline
when real providers return thin results. Chat completions do not browse, so this needs a search API
(see `spec/data-sources.md`).
