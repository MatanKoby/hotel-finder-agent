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

With a **LiteAPI key** and a **Nebius key** in `.env`, a user runs the **interactive CLI**, types
a location, and gets **real** hotels and accommodations nearby (real names, descriptions,
coordinates, and **prices** from LiteAPI), organized across the **three lenses**, **scored by the
Nebius LLM** (heuristic fallback on failure). Everything flows through the submodule **`search()`
API** (`HotelSearchRequest` → `HotelSearchResponse` envelope, see `spec/contract.md`). **No mock
data in the live path, no crashes:** data problems become `warnings` + `status`, never exceptions.

M1 is the set of batches **M1a–M1e** below. The v1 vertical slice (mock provider, pipeline,
scorers, lenses, 26 tests) is already done (see `spec/roadmap.md` → Status). Post-M1 batches follow.

> **Pick-order pointer for "continue".** After a context clear, **ask** which un-done batch to
> claim rather than guessing. **M1a is the foundation** (the contract everything else builds on);
> M1b/M1c/M1e can follow it in parallel; **M1d integrates them last**.

---

## Batch M1a — Contract refactor to the submodule search API

**Milestone 1. Foundation** for every other M1 batch. Decision is settled → **ready**.

**Depends on:** none.

**Goal.** Refactor `contracts.py` from the v1 `HotelQuery` / `Recommendations` to the submodule
API in `spec/contract.md`: a validated `HotelSearchRequest` in, a `HotelSearchResponse` envelope
out, exported so an orchestrator can validate input on its own side before calling.

### Deliverables
- Request models: `Place` (structured `country_code`+`city` / `center`+`radius_km`, plus a
  `text` geocode fallback and `desired_area`), `Occupancy`, `Stay` (optional), `Filters`,
  `HotelSearchRequest`. Validators for price and date ranges; `extra="forbid"`.
- Response models: `RateOffer` (total/currency/per_night/board/refundable, no booking token),
  `ResolvedQuery`, `Pick` (adds `offer`), `HotelSearchResponse` (`status` ok/empty/degraded +
  `warnings`, never raises for a data outcome).
- `async def search(request, settings=None) -> HotelSearchResponse` entry point; re-export
  `search`, `HotelSearchRequest`, `HotelSearchResponse` (and sub-models) from
  `hotel_finder/__init__.py`.
- Pipeline produces the envelope (populates `status`, `warnings`, `resolved`) instead of raising
  on empty/degraded outcomes.

### Files this batch creates/edits
- `src/hotel_finder/contracts.py` (rewrite), `src/hotel_finder/__init__.py` (exports),
  `src/hotel_finder/pipeline.py` (build envelope; map `Place`/`Stay`), `stages/explain.py`
  (`Pick.offer`), `demo.py` (new names, minimal), `tests/` (validation raises at construction;
  envelope status/warnings; content-only when `stay` omitted).

### Does NOT touch
- Scoring math; the LiteAPI provider (M1b); the geocoding impl (M1c) — the `text` fallback can be
  a stub here.

### Verification
- `make check` green; a `HotelSearchRequest` built from a mapping validates and a malformed one
  raises `ValidationError` at construction; `search()` returns a `HotelSearchResponse` envelope.

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
  description, stars, guest `rating`, `review_count`, amenities via `normalize_amenities`) and
  the priced rate to a `RateOffer` (total/currency/per_night/board/refundable).
- Registered in `providers/registry.py`; runs when `liteapi` is in `enabled_providers`; upstream
  errors are caught and surfaced as `warnings`, never fatal.
- Offline test from a **recorded** LiteAPI payload (no network in CI); secrets via `.env` only.

### Files this batch creates/edits
- `src/hotel_finder/providers/liteapi/` (new), `providers/registry.py`, `config.py`
  (`LITEAPI_API_KEY`, base URL — additive), `.env.example`, `tests/` (recorded-payload fixture).

### Does NOT touch
- The mock provider, pipeline stages, scoring math, the CLI.

### Verification
- `make check` green with `liteapi` disabled by default; an integration test drives the adapter
  from a recorded payload and yields valid `Hotel`s with a `RateOffer`.

---

## Batch M1c — Place resolution (structured passthrough + text geocoding)

**Milestone 1.** Turns `Place` into what LiteAPI and distance ranking need. Ready.

**Depends on:** M1a (defines `Place`). Pairs with M1b.

**Goal.** Resolve `Place`: use `country_code`+`city` or `center` directly when given; when only
`text` is given, geocode it (free Nominatim, or LiteAPI's place lookup) into `country_code`+`city`
and/or a `center` GeoPoint. Record what was resolved in `ResolvedQuery`. Graceful, non-fatal
fallback when geocoding fails (warn, proceed with what is known).

### Deliverables
- A geocoder helper behind an interface (offline test double), free backend, rate-limit aware
  (`User-Agent` header for Nominatim, see `spec/data-sources.md`).
- Pipeline resolves `Place` before provider dispatch and fills `resolved` on the response; a
  geocode failure adds a `warning` and does not crash.

### Files this batch creates/edits
- `src/hotel_finder/utils/geocode.py` (new), `src/hotel_finder/pipeline.py` (resolve step),
  `config.py` (geocoder endpoint — additive), `tests/` (offline geocoder double).

### Does NOT touch
- Scoring math, provider adapters, the CLI.

### Verification
- `make check` green; a request with only `place.text` resolves to a `center`/city in a test
  using the double, and a forced geocode failure yields a warning, not an exception.

---

## Batch M1d — Interactive CLI (the visible end-to-end demo)

**Milestone 1. Integrates M1a–M1c** into the runnable experience the DoD describes. Ready.

**Depends on:** M1a, M1b, M1c.

**Goal.** An interactive CLI: prompt for a location (and optionally dates/guests), build a
`HotelSearchRequest`, call `search()` against **live LiteAPI** with the **Nebius** scorer, and
print real results across the three lenses, including prices. Reads keys from `.env`
(`spec/config.md`, `spec/dev-guide.md`).

### Deliverables
- Interactive prompt loop (location required; dates/guests optional → content-only vs priced).
- Renders the three lenses with name, area, price (`RateOffer`), guest rating, and rationale;
  prints `status` + any `warnings` plainly.
- A non-interactive flag path (e.g. `--location`) is retained for scripted runs/tests.

### Files this batch creates/edits
- `src/hotel_finder/demo.py` (or a new `cli.py`), `tests/` (drive the CLI with a stubbed
  `search`/provider; assert lenses + warnings render).

### Does NOT touch
- Contract models, provider internals, scoring math.

### Verification
- `make check` green; with keys set, `python -m hotel_finder ...` (or the CLI entry) returns real
  LiteAPI hotels with prices across three lenses; missing/invalid keys degrade gracefully with a
  warning, not a crash.

---

## Batch M1e — Nebius LLM scoring end to end + effective-scorer reporting

**Milestone 1.** Makes "scored by the Nebius LLM, heuristic fallback" real and observable. Ready.

**Depends on:** M1a (envelope `warnings` / `meta`).

**Goal.** Verify the existing `LLMScorer` reaches **Nebius Token Factory** via env with no code
change (`spec/scoring.md`, `spec/config.md`), and make fallback observable: `meta.scorer` reports
the scorer that **actually ran**, and a fallback adds a `warning`. (Folds the former "meta.scorer
effective" polish into M1.)

### Deliverables
- On LLM fallback (no key / error / omitted ids), `meta.scorer` reads `heuristic` and a `warning`
  records the fallback; the happy LLM path reads `llm`; heuristic-configured runs read `heuristic`.
- A short doc/verification note that Nebius env values (`LLM_BASE_URL`, `LLM_API_KEY`,
  `LLM_MODEL`, `SCORER=llm`) drive real scoring end to end.

### Files this batch creates/edits
- `src/hotel_finder/scoring/base.py` and/or `scoring/llm.py` (surface the effective scorer),
  `src/hotel_finder/pipeline.py` (set `meta.scorer` + fallback warning), `tests/` (forced
  fallback reports `heuristic` + emits a warning).

### Does NOT touch
- Scoring math / weightings, provider adapters, the CLI.

### Verification
- `make check` green; a forced-fallback request reports `scorer=heuristic` with a warning; a
  configured LLM run reports `llm`.

---

## Post-M1 batches

These are out of scope for Milestone 1 and unblock after it lands.

### Batch P1 — Lens-aware rationales in `explain.py`

**Depends on:** M1a. **Goal.** Per-lens phrasing so a hotel under `hidden_gems` reads differently
from the same data under `stratified_best` (`spec/pipeline.md` → Explain/Lenses), deterministic
(no LLM). Edits `stages/explain.py` (+ `pipeline.py` if it needs the lens), `tests/` for distinct
phrasings. Does not touch scoring or the `Pick` shape.

### Batch P2 — `ANCHOR` intent (peers of a named hotel)

**Depends on:** M1b (a source that can resolve a named hotel; LiteAPI can). **Open scope** →
resolve with the user via `spec-edit` before claiming. **Goal.** Implement the reserved `anchor`
intent: resolve `anchor_hotel` to a band/area/rating envelope, then find peers within it
(`spec/contract.md` → `Intent`, `spec/roadmap.md`). Edits `pipeline.py` (intent branch), maybe
`stages/anchor.py`, `tests/`. `zone` behavior unchanged.

### Batch P3 — Additional data sources / multi-source blend

**Depends on:** M1b. **Open scope** → `spec-edit` first. **Goal.** Add further sources from
`spec/data-sources.md` → Future direction: an OSM breadth/fallback layer, an independent price
cross-check (Amadeus test / Xotelo `/rates`), or OpenTripMap/LLM descriptions. Each is a provider
folder per `spec/providers.md`; cross-source dedupe stays in the pipeline.

### Batch P4 — LLM web-search backup source

**Depends on:** M1b. **Open scope** → `spec-edit` first. **Goal.** The deferred backup from
`spec/roadmap.md` (M1 Approved → web search is secondary): a separate search tool/API feeding the
pipeline when real providers return thin results. Chat completions do not browse, so this needs a
search API (see `spec/data-sources.md`).

### Batch P5 — Tuning and widening polish

**Depends on:** none. **Goal.** Revisit the reasonable-but-untuned defaults flagged in
`spec/roadmap.md` → Open considerations: heuristic weightings/thresholds (`spec/scoring.md`),
price-band cutoffs (`spec/config.md`), and gentler filter widening (`spec/pipeline.md`, which
today drops price bounds entirely).
