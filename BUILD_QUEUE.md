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

**Milestone 1 (batches M1a–M1e) is COMPLETE** — see `specflow/history/BUILD_QUEUE_DONE.md` and
`CLAIMS.md` → Completed. hotel-finder is submodule-ready: import → `HotelSearchRequest` →
`search()` → `HotelSearchResponse` with real LiteAPI hotels/prices across three lenses, Nebius LLM
scoring with heuristic fallback, free-text geocoding, no mandatory `.env`, no crashes. The remaining
batches below are **post-M1** (evaluation and quality).

> **Pick-order pointer for "continue".** M1 is done. The next work is the **contract reshape**:
> **C1** (flatten Pick + renames + trip-level guests), then **C2** (provider-backed `image_url` /
> `distance_to_desired_km`) — the M1 contract was renegotiated with the orchestrator (see
> `spec/contract.md`). After those, **P1** (evaluation harness), then **P2** (quality); P3/P4/P5 are
> open-scope and need a `spec-edit` first. Claim via `specflow/procedures/claim-batch.md`, record in
> `CLAIMS.md`, `make check` as the gate.

---

## Contract reshape (post-M1, orchestrator-agreed)

The M1 contract was renegotiated with the orchestrator ("tripper") after M1 shipped — see
`spec/contract.md` → **Status vs the current code**. These two batches move the code from the nested
M1 shape to the agreed flat/renamed wire shape. **Land before P1** so the eval harness targets the
final contract. C1 does the pure-shape refactor (no new provider data); C2 populates the two fields
C1 declares nullable.

### Batch C1 — Contract reshape (flatten Pick, renames, trip-level guests)

**Depends on:** M1e. **Goal.** Refactor `contracts.py` and the response/request-building stages to
the wire shape in `spec/contract.md`, with **no new provider data** (the two new fields return
`None` here, populated in C2).

- **Request:** add trip-level `guests: Occupancy` (default `Occupancy()`) and
  `guest_nationality: str = "US"`; change `Stay.rooms` to `list[Occupancy] | None = None` (`None`
  derives one room from `guests`; a set value **overrides** `guests`); remove `guest_nationality`
  from `Stay`. `intent`/`anchor_hotel` stay on the model with inert defaults (`zone`/`None`) but out
  of the documented wire.
- **Response:** rename `status` → `agent_status`, rename `meta` → `diagnostics` (rename
  `RecommendationMeta` → `Diagnostics`), add `area` to `ResolvedQuery`.
- **Pick (flatten):** surface `name` / `area` / `price_per_night` / `currency` / `rating` /
  `review_count` / `star_rating` / `description` / `amenities` / `url` up from the hotel (drop the
  nested `hotel`, and `raw` / full `sources` from the wire); rename the wire field `subscores` →
  `why` (internal `ScoredHotel.subscores` is unchanged — `explain.py:18` maps it); bound `score`
  with `Field(ge=0, le=1)`; declare `image_url: str | None` and `distance_to_desired_km: float |
  None`, both returning `None` in this batch.
- **Pipeline:** derive `[guests]` when `stay.rooms is None`; thread trip-level `guest_nationality`
  onto the rate call; `explain.py` builds the flat `Pick` (maps `subscores → why`).
- **Callers/tests:** update `examples/orchestrator_sim.py` (render `pick.name`, `agent_status`,
  `diagnostics`) and all affected tests; add a test asserting `Pick.score ∈ [0, 1]` and that the
  same overall score is carried across lenses (no per-tier re-normalization).
- **Files:** `src/hotel_finder/contracts.py`, `src/hotel_finder/pipeline.py`,
  `src/hotel_finder/stages/explain.py`, `examples/orchestrator_sim.py`, `tests/**`. **Gate:**
  `make check` green.

### Batch C2 — Provider-backed enrichment (`image_url`, `distance_to_desired_km`)

**Depends on:** C1. **Goal.** Populate the two fields C1 declared nullable.

- **`image_url`:** add `image_url: str | None` to `Hotel` (`models.py`, per `spec/domain-model.md`);
  map LiteAPI `main_photo` / `thumbnail` (today kept in `raw`) in the liteapi adapter; mock leaves
  it `None`; surface it in `explain.py`'s flat `Pick`.
- **`distance_to_desired_km`:** compute in `explain.py` via `utils/geo.py` `haversine` to
  `resolved.center` / the desired-area point; `None` when neither is available.
- **Verify** `review_count` and `description` populate end-to-end from LiteAPI (both already on
  `Hotel`; C1 surfaces them — confirm they aren't silently `None`).
- **Files:** `src/hotel_finder/models.py`, `src/hotel_finder/providers/liteapi/adapter.py`,
  `src/hotel_finder/stages/explain.py`, `tests/**`. **Gate:** `make check` green.

## Post-M1 batches (testing, evaluation, quality)

Out of scope for M1; unblock after it lands. M1 ships the capability; these make it work *well*.

### Batch P1 — Evaluation harness and test scenarios

**Depends on:** C1 (target the reshaped contract). **Goal.** Start testing it actually works
properly: representative scenarios (cities, budgets, `refundable` variants, over-budget fallback,
content-only) driven through `search()` via the orchestrator wrapper, with quality
assertions/metrics (lenses populated, prices present, dedupe sane, `agent_status`/`warnings`
correct). Establishes the baseline for improving results. Lands under `tests/eval/` (or
`examples/eval/`).

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
