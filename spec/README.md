# Specification

**hotel-finder** is a hotel-recommending agent: one of three agents in a travel planner
(separate devs own a **flights** agent and an **activities/itinerary** agent; the orchestration
layer above the three is out of scope for now). Given a location and constraints, it recommends
where to stay across three "lenses": best value per price tier, overall standouts, and hidden
gems. It is **stateless / idempotent** (a self-contained `HotelSearchRequest` in, a
`HotelSearchResponse` out) and **Python is a hard requirement**.

Status: **v1 vertical slice complete and verified** (26 tests passing, ruff + mypy clean).
Greenfield project; Python 3.12; managed with `uv`.

The spec is split across concern-focused files. Each file is small and edited as a unit. When
two sections always change in tandem, they belong in the same file. Edit via the procedure in
`specflow/procedures/spec-edit.md`.

## Files

- **`architecture.md`** — the core design decisions and their rationale, the source-tree file
  map, and the tech stack. Start here after this README.
- **`domain-model.md`** — canonical domain types (`Hotel`, `GeoPoint`, `PriceBand`, `Amenity`)
  and amenity normalization (`models.py`).
- **`contract.md`** — the submodule `search()` API and request/response contract:
  `HotelSearchRequest`, `HotelSearchResponse`, `Place`, `Stay`, `RateOffer`, `Pick` (`contracts.py`).
- **`providers.md`** — the pluggable data-provider architecture (one folder per source:
  `api.py` + `adapter.py`).
- **`data-sources.md`** — external catalog of evaluated real hotel/accommodation APIs, what each
  offers, live-test findings, and the chosen M1 source (LiteAPI).
- **`pipeline.md`** — the deterministic orchestrator sequence (`search()`) and every stage
  in detail (dedupe, filter + widening, shortlist, lenses, explain).
- **`scoring.md`** — the one LLM-or-heuristic step: the `HotelScorer` interface, the heuristic
  default, and the opt-in LLM scorer.
- **`config.md`** — `Settings` (env + `.env`): providers, scorer, LLM endpoint, thresholds,
  price-band cutoffs.
- **`dev-guide.md`** — running, testing, tooling, and how to extend (add a source / scorer /
  lens / helper).
- **`roadmap.md`** — v1 status, what is out of scope, candidate next steps, and open
  considerations to revisit.

## Reading order

For someone new: README → `architecture.md` → the files for the area in front of them. Don't
read everything. The contract (`contract.md`) and domain model (`domain-model.md`) are the two
worth reading before any implementation work.

For an agent claiming a batch: read the queue entry first, then the 2 to 4 spec files relevant
to the batch's domain.

## Editing convention

Edit the file matching the concern. If a change crosses multiple files, that's a signal the
concern might be miscarved: flag it before duplicating content. Cross-reference by file path
rather than restating. Move historical context to `roadmap.md` (or a future `archive.md`) when
it stops being part of the live system. Full procedure: `specflow/procedures/spec-edit.md`.
