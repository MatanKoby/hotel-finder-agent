# Architecture

Product identity is in `README.md`. This file captures the decisions that shape the whole
system, the source-tree map, and the tech stack. Per-area detail lives in the concern files
linked below.

## Guiding principle

**Intelligence in the steps, orchestration in plain code.** The pipeline is deterministic; the
only place that wants judgment (fuzzy scoring) is isolated behind an interface.

The agent is **stateless / idempotent**: a self-contained `HotelQuery` in, a `Recommendations`
out, no memory between calls (see `contract.md`). This deliberately dissolves the "one big
orchestrator call vs many small calls" question: the agent behaves identically either way, so
that decision can be deferred to whoever builds the orchestrator.

## Core decisions (and why)

| Decision | Rationale |
|---|---|
| **Deterministic pipeline, not a free-roaming LLM agent** | The stages are fixed and known up front and never branch on what's found. A self-directing agent loop only earns its cost when control flow is data-dependent and unknowable; here it would add latency, token cost, and nondeterminism (which makes evaluation and unit-testing hard). |
| **Pluggable data providers (Strategy/Adapter)** | The real work is normalization. One interface; each source is a folder. Adding a source touches no core code. See `providers.md`. |
| **One LLM step, behind an interface** | Only the fuzzy scoring step wants judgment. Isolating it behind `HotelScorer` keeps the rest deterministic and testable and makes the LLM optional and swappable. See `scoring.md`. |
| **Mock/fixture provider first** | Lets the whole pipeline (including scoring) build, run, and be evaluated offline and at $0, before integrating any real or paid source. |
| **Heuristic scorer is the default; LLM is opt-in** | The user cannot afford a paid model API. The heuristic scorer is free, deterministic, and good enough to make everything runnable and evaluable. The LLM scorer is enabled only when a (free) key is configured. |
| **LLM scorer is provider-agnostic (Groq by default)** | Uses the OpenAI-compatible API. No Anthropic/paid dependency. Default endpoint is Groq's free tier; switching to xAI Grok / OpenRouter is an env change, not a code change. Always falls back to the heuristic on any error. |
| **Per-provider folder layout** | User preference: each provider folder owns exactly two concerns, `api.py` (fetch raw) plus `adapter.py` (normalize to our types). Cross-provider concerns (dedupe) live in the pipeline. Filesystem readable at a glance; helpers go in `utils/`. |
| **Pydantic v2 everywhere** | Validation, clean JSON for LLM I/O, and a stable typed contract that the future orchestrator and adapters hang off. |

## File map

```
src/hotel_finder/
  __init__.py        # re-exports recommend() — the agent's single public entry point
  models.py          # canonical domain types: Hotel, GeoPoint, PriceBand, Amenity (+ normalization)
  contracts.py       # request/response: HotelQuery, Recommendations, Pick, RecommendationMeta, Intent, LensName
  config.py          # Settings (pydantic-settings; env + .env); price-band cutoffs; pipeline thresholds
  pipeline.py        # recommend() — the deterministic orchestrator
  demo.py            # argparse CLI: python -m hotel_finder.demo

  utils/             # cross-cutting helpers (no domain meaning)
    geo.py           #   haversine(GeoPoint, GeoPoint) -> km   (the ONLY distance math)
    text.py          #   normalize_text() — lowercase/strip-accents/collapse, for fuzzy name/area match

  providers/         # DATA PROVIDERS — one self-contained folder per source (see providers.md)
    base.py          #   ProviderApi, HotelAdapter, HotelProvider protocols + ComposedProvider
    registry.py      #   register / get_provider / get_providers; built-ins register at import
    mock/
      api.py         #   MockApi.fetch(query) -> list[raw dict]   (reads fixtures, ignores query)
      adapter.py     #   MockAdapter.to_hotel(raw) -> Hotel
      fixtures/barcelona.json   # 14 hotels across all price bands incl. a planted hidden gem

  stages/            # DETERMINISTIC PIPELINE STEPS (one concern per file; see pipeline.md)
    dedupe.py        #   cross-provider merge by normalized-name + proximity
    filtering.py     #   FilterCriteria + hard_filter (amenities, price, area radius)
    shortlist.py     #   cheap pre-rank, keep top ~N
    lenses.py        #   stratified_best / overall_standouts / hidden_gems (pure fns)
    explain.py       #   ScoredHotel -> Pick (attaches rationale + surfaces coordinates)

  scoring/           # THE ONE LLM-OR-HEURISTIC STEP (see scoring.md)
    __init__.py      #   make_scorer(settings) -> HotelScorer
    base.py          #   HotelScorer protocol, ScoredHotel, overall_score() (the score weighting)
    heuristic.py     #   HeuristicScorer — free, deterministic default
    llm.py           #   LLMScorer — OpenAI-compatible (Groq default), Pydantic-validated, heuristic fallback

tests/               # 26 tests, fully offline (LLM path uses a stubbed client)
```

## Tech stack

Python 3.12, managed with `uv`. Runtime deps: `pydantic`, `pydantic-settings`, `openai`. Dev
deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy`. Full tooling config, commands, and extension
points are in `dev-guide.md`.
