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

> **Pick-order pointer for "continue".** "Continue working towards the first milestone" means:
> claim and build the remaining M1 batches in order. **M1a (the foundation) is done** (see
> `specflow/history/BUILD_QUEUE_DONE.md`); next are **M1b/M1c/M1d** (parallelizable, all depend
> only on M1a), then **M1e** (integration surface + example, integrates last). Claim each via
> `specflow/procedures/claim-batch.md`, record it in `CLAIMS.md`, and run `make check` as the gate.
> Only if the instruction is genuinely ambiguous, ask which batch.

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
