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
> the **result-quality pass (P2)** shipped (findings 1-5), and the **`anchor` intent (P3)** shipped
> (peer envelope + exclusion + zone fallback — see `CLAIMS.md` → Completed and `spec/pipeline.md` →
> Anchor intent).
> **Next up: Batch P7** (refinement / feedback-loop entry point) is **specced and ready to claim** —
> `refine(HotelRefineRequest)` with a stable `Pick.id`, see `spec/contract.md` → Refinement and
> `spec/pipeline.md` → Refine.
> The remaining batches — **P4** (more sources), **P5** (web-search backup) — are both **open-scope**
> and need a `spec-edit` first. Two M1 correctness flags are also still open (each needs a `spec-edit`
> first): `filters.property_types` is accepted but unenforced, and `over_budget` is computed per-night
> while `spec/contract.md` phrases the budget as a total. Eval finding 6 (semantic/quality metrics,
> not just structure) is also open. Claim via `specflow/procedures/claim-batch.md`, record in
> `CLAIMS.md`, `make check` as the gate.

---

## Post-M1 batches (testing, evaluation, quality)

Out of scope for M1; unblock after it lands. M1 ships the capability; these make it work *well*.

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

### Batch P7 — Refinement entry point (feedback loop)

**Depends on:** M1 (shipped). **Specced** (this batch's design is in `spec/`, ready to build).
**Goal.** A second stable entry point `refine(HotelRefineRequest)` (+ `refine_sync`), returning the
same `HotelSearchResponse` as `search`, so the orchestrator runs a two-call loop: `search`, then
`refine` with the user's wanted / unwanted marks. Full contract + behavior:
`spec/contract.md` → Refinement, `spec/pipeline.md` → Refine, `spec/config.md` → Refine knobs,
`spec/scoring.md` → Preference bias.

**Scope.**
- **Contract** (`contracts.py`): add `Pick.id` (`"{source}:{id}"`), `HotelFeedback` +
  `HotelFeedbackAttributes`, `HotelRefineRequest` (`base` / `wanted` / `unwanted` / `exclude` /
  `round`), `Diagnostics.refined` + `round`; export `refine`, `refine_sync`, `HotelRefineRequest`,
  `HotelFeedback`. Set `Pick.id` in `stages/explain.py`.
- **Stage** `stages/refine.py`: `resolve_feedback` (id then normalized-name match), `exclusion_ids`
  (wanted ∪ unwanted ∪ exclude), `RefineEnvelope` from the wanted set (multi-hotel analogue of the
  anchor envelope, tighten-only + re-centre on the centroid), `apply_preference` (bounded post-scoring
  nudge, surfaced as `why["preference"]`).
- **Pipeline** (`pipeline.py`): `refine()` async + `refine_sync()`; extract the shared tail of
  `search()` so both entry points assemble the response through one path; thread wanted/unwanted
  preference onto the scorers via `SearchContext`. Add `refine_*` knobs to `config.py`.
- **Scoring**: wanted/unwanted profiles + `reason` text into the LLM prompt (`scoring/llm.py`); the
  deterministic nudge in `apply_preference` covers the heuristic path.
- **Tests** `tests/test_refine.py` (offline mock + heuristic, under `make check`): response shape,
  **unwanted absent**, **wanted-like favored**, statelessness / id round-trip. Live path validated
  via `make eval` (the repo has no live pytest tests to mark).

**Done.** From a clean env with no secrets: `refine_sync(HotelRefineRequest(base=<minimal
HotelSearchRequest>, wanted=[...], unwanted=[...]))` imports and returns a structured
`HotelSearchResponse` with the unwanted properties excluded and wanted-like properties favored.
`make check` green.

