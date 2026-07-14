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

> **Pick-order pointer for "continue".** M1 is done, the **contract reshape (C1 + C2)** shipped, the
> **evaluation harness (P1)** shipped, its **live-run wiring + LLM thinking-off toggle (P6)** shipped,
> and the **result-quality pass (P2)** shipped (findings 1-5: star-tier lens fallback, desired-area
> ranking point, grounded heuristic/LLM location, honest gem rationales, gentle price widening — see
> `CLAIMS.md` → Completed).
> The remaining batches — **P3** (anchor intent), **P4** (more sources), **P5** (web-search backup) —
> are all **open-scope** and need a `spec-edit` first. Two M1 correctness flags are also still open
> (each needs a `spec-edit` first): `filters.property_types` is accepted but unenforced, and
> `over_budget` is computed per-night while `spec/contract.md` phrases the budget as a total. Eval
> finding 6 (semantic/quality metrics, not just structure) is also open. Claim via
> `specflow/procedures/claim-batch.md`, record in `CLAIMS.md`, `make check` as the gate.

---

## Post-M1 batches (testing, evaluation, quality)

Out of scope for M1; unblock after it lands. M1 ships the capability; these make it work *well*.

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

