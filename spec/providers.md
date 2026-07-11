# Data providers (`providers/`)

This file is the **internal architecture** (how a source plugs in). Which real external APIs were
evaluated and chosen (LiteAPI for M1) is the **external catalog** in `data-sources.md`.

Pluggable data sources behind one interface. The real work here is **normalization**: turning
each source's native payload into the domain types in `domain-model.md`. Adding a source touches
no core code (see `dev-guide.md` → Add a data source). Cross-provider concerns (dedupe) do not
live here; they live in the pipeline (`pipeline.md`).

## Two concerns per provider, in two files

- **`api.py` — the provider API.** Talks to the source and returns **raw** records in its native
  shape: `async def fetch(self, query: HotelSearchRequest) -> list[dict]`. (Mock reads `fixtures/*.json`
  and ignores the query; a real one builds an HTTP request; a scraper fetches and parses.)
- **`adapter.py` — the provider adapter.** `def to_hotel(self, raw: dict) -> Hotel`. All
  **per-source** normalization lives here: field mapping, amenity-vocab mapping (via
  `normalize_amenities`, see `domain-model.md`), coord parsing, provenance tag. Price-band
  **derivation from a bare price** is a global policy and happens in the pipeline using
  configured thresholds, not in the adapter (see `config.md`, `pipeline.md`).

## `base.py`

Defines the `ProviderApi`, `HotelAdapter`, and `HotelProvider` protocols plus
**`ComposedProvider(name, api, adapter)`**: a frozen dataclass whose `search()` does *fetch →
map each record through the adapter*. Most providers need only the two files; a source needing
bespoke flow (pagination, multi-call) can implement `HotelProvider` directly.

## `registry.py`

Maps name → provider (`register`, `get_provider`, `get_providers`). Built-ins register at
import:

```python
register(ComposedProvider("mock", MockApi(), MockAdapter()))
```

**The pipeline depends only on `HotelProvider`.** Which providers actually run is controlled by
`enabled_providers` in `config.md`.

## The mock provider

`providers/mock/` is the fixture source that makes the whole system runnable offline at $0.
`MockApi.fetch` reads `fixtures/barcelona.json` (14 hotels across all price bands, including a
planted hidden gem) and ignores the query; `MockAdapter.to_hotel` normalizes each record. Known
limitation: the mock ignores the query and returns its whole fixture city (see `roadmap.md`).
