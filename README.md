# hotel-finder

A hotel-finding agent for a travel planner. Given a location and constraints, it recommends
where to stay across three lenses: **best value per price tier**, **overall standouts**, and
**hidden gems**.

It's a **deterministic pipeline** — gather → dedupe → filter → shortlist → score (once) →
lenses → explain — with **pluggable data providers** and a **pluggable scorer**. Intelligence
lives in the steps; orchestration is plain, testable code. The agent is stateless: request in,
recommendations out.

## Quick start

```bash
make install                 # uv sync (creates .venv, installs deps)
make run                     # run the demo on bundled mock data (offline, $0)
make check                   # ruff + mypy + pytest
```

Or directly:

```bash
uv run python -m hotel_finder.demo --location Barcelona
uv run pytest
```

## Architecture

```
src/hotel_finder/
  models.py        # canonical Hotel, GeoPoint, PriceBand, amenity vocab
  contracts.py     # HotelQuery (request), Recommendations (response), Pick, Intent
  config.py        # Settings (env + .env)
  pipeline.py      # recommend() — the deterministic orchestrator
  utils/geo.py     # haversine distance
  providers/       # one self-contained folder per data source
    base.py        #   ProviderApi + HotelAdapter + HotelProvider protocols; ComposedProvider
    registry.py    #   name -> provider
    mock/          #   api.py (fetch raw) + adapter.py (raw -> Hotel) + fixtures/
  stages/          # deterministic pipeline steps: dedupe, filtering, shortlist, lenses, explain
  scoring/         # the one heuristic-or-LLM step (HotelScorer)
```

**Adding a data source** = a new `providers/<name>/` folder with `api.py` (fetch raw) and
`adapter.py` (normalize raw → `Hotel`), registered in `providers/registry.py`. No core changes.

## Scoring

The single LLM step is isolated behind a `HotelScorer` protocol:

- **`heuristic`** (default): deterministic, free, offline — runs and unit-tests with no key.
- **`llm`** (opt-in): an OpenAI-compatible endpoint (Groq by default; swap for xAI Grok /
  OpenRouter via env). Falls back to the heuristic scorer on any error.

Enable the LLM path by copying `.env.example` to `.env`, setting `LLM_API_KEY` + `LLM_MODEL`,
and running with `SCORER=llm` (or `--scorer llm`).
