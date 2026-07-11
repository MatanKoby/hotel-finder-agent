# hotel-finder

A hotel-finding agent for a travel planner, designed to be embedded as a **git submodule** in an
orchestrator agent. Given a location and constraints it recommends where to stay across three
lenses: **best value per price tier**, **overall standouts**, and **hidden gems**.

It's a **deterministic pipeline** — resolve → gather → dedupe → filter → shortlist → score (once) →
lenses → explain — with **pluggable data providers** and a **pluggable scorer**. Intelligence lives
in the steps; orchestration is plain, testable code. The agent is stateless: a
`HotelSearchRequest` in, a `HotelSearchResponse` envelope out. **There is no interactive CLI.**

## Use as a submodule

Add it to the orchestrator and install it (editable) into the same environment:

```bash
git submodule add https://github.com/MatanKoby/hotel-finder.git vendor/hotel-finder
pip install -e vendor/hotel-finder
```

Then build a request from the exported Pydantic models and call `search()`:

```python
from datetime import date
from hotel_finder import search, HotelSearchRequest, Place, Stay, Filters

request = HotelSearchRequest(
    place=Place(country_code="ES", city="Barcelona", desired_area="El Born"),
    stay=Stay(check_in=date(2026, 8, 1), check_out=date(2026, 8, 4)),
    filters=Filters(price_max=250, min_guest_rating=8.0),
)

response = await search(request)          # async entry point
# response = search_sync(request)         # blocking wrapper for non-async callers

for lens, picks in response.lenses.items():
    for pick in picks:
        print(lens, pick.hotel.name, pick.score, pick.offers)
```

The Pydantic models **are the shared validator**: the orchestrator constructs `HotelSearchRequest`
on its own side, so a malformed request raises `pydantic.ValidationError` at construction, before
`search()` runs. During work the agent never crashes — data problems (a provider down, nothing in
budget, the LLM unavailable) become `response.warnings` + `response.status`
(`ok` / `empty` / `degraded`), never exceptions. `model_json_schema()` is available if the caller
wants the request schema as a tool definition.

Config is injected or read from the environment — **no `.env` is required when imported**. Pass a
`Settings` to override: `search(request, Settings(enabled_providers=["liteapi"], scorer="llm"))`.

## Quick start (local dev)

```bash
make install                 # uv sync (creates .venv, installs deps)
make run                     # examples/orchestrator_sim.py on bundled mock data (offline, $0)
make check                   # ruff + mypy + pytest
```

`examples/orchestrator_sim.py` stands in for the orchestrator. With no configuration it uses the
**mock** provider + **heuristic** scorer, fully offline. Point it at real services via env:

```bash
ENABLED_PROVIDERS=liteapi LITEAPI_API_KEY=sand_... SCORER=llm LLM_API_KEY=... make run
```

## Data + scoring

- **Data providers** (`ENABLED_PROVIDERS`): `mock` (bundled fixtures, default) and **`liteapi`**
  (real hotels, content, and prices from LiteAPI/Nuitée; free sandbox key). Adding a source = a new
  `providers/<name>/` folder (`api.py` + `adapter.py`) registered in `providers/registry.py`.
- **Scorer** (`SCORER`): `heuristic` (deterministic, free, offline — the default) or `llm` (opt-in).
  The LLM scorer has two transports, both contacted by this repo and selected by `LLM_BACKEND`:
  an **OpenAI-compatible** endpoint (`LLM_API_KEY`, e.g. Nebius Token Factory / Groq) for local eval,
  and a shared **Nebius serverless endpoint** (`NEBIUS_ENDPOINT_URL`, Ollama REST, no key) for the
  orchestrator. It **falls back to the heuristic** on any failure, and `meta.scorer` reports the
  scorer that actually ran.

See `.env.example` for every setting, and `spec/` for the full design.

## Layout

```
src/hotel_finder/
  models.py        # canonical Hotel, GeoPoint, PriceBand, amenity vocab
  contracts.py     # HotelSearchRequest / HotelSearchResponse, Pick, RateOffer, ...
  context.py       # internal SearchContext (resolved params for the stages)
  config.py        # Settings (env + .env)
  pipeline.py      # search() / search_sync() — the deterministic orchestrator
  utils/           # geo.py (haversine), text.py, geocode.py (Nominatim)
  providers/       # one self-contained folder per data source (base, registry, mock/, liteapi/)
  stages/          # dedupe, filtering, shortlist, lenses, explain
  scoring/         # HotelScorer: heuristic + LLM (OpenAI-compatible / Nebius endpoint)
examples/orchestrator_sim.py   # runnable orchestrator stand-in (make run)
```
