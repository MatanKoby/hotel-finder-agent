# Dev guide: running, testing, tooling, extending

How to run the agent, the tooling contract, and where the extension points are. The design each
of these touches lives in the concern files linked below.

## Running and testing

```bash
make install            # uv sync (creates .venv, installs runtime + dev deps)
make run                # run examples/orchestrator_sim.py (drives search() like the orchestrator)
make check              # ruff + mypy + pytest
# or:
uv run python examples/orchestrator_sim.py
uv run pytest
```

There is no interactive CLI: hotel-finder is a library/submodule. `examples/orchestrator_sim.py` is
the runnable example; the orchestrator imports `search` directly (see `contract.md`).

**Real data + LLM scoring:** copy `.env.example` → `.env`. Set `LITEAPI_API_KEY` for real hotels
(see `data-sources.md`). For scoring, pick a Nebius run mode (`config.md` → LLM run modes): a Token
Factory `LLM_API_KEY` + `LLM_MODEL` for local eval, or `NEBIUS_ENDPOINT_URL` +
`NEBIUS_ENDPOINT_TOKEN` for the shared serverless endpoint; then `SCORER=llm`. With neither, it
warns and uses the heuristic (see `scoring.md`).

**Local dev (orchestrator simulator):** `examples/orchestrator_sim.py` drives the `search()` API
the way the orchestrator will (build `HotelSearchRequest` → `await search()` → read the
`HotelSearchResponse` envelope), so the submodule contract runs end to end locally with a Token
Factory key (heuristic without one). Systematic evaluation is post-M1. See `BUILD_QUEUE.md` → M1e.

## Tooling

`uv` manages deps and the venv. Runtime deps: `pydantic`, `pydantic-settings`, `openai`. Dev
deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy` (all in `pyproject.toml`).

- **ruff** lint + format (line length 100; rules E, F, I, UP, B, SIM).
- **mypy** `strict`, scoped to `src` (tests use untyped doubles), pydantic plugin enabled.
- **pytest** `asyncio_mode=auto` (async tests need no decorator). 26 tests, fully offline (the
  LLM path uses a stubbed client).
- `Makefile` targets: `install / lint / format / typecheck / test / check / run`.
- Public entry re-exported: `from hotel_finder import search` (plus `HotelSearchRequest` /
  `HotelSearchResponse`).

## How to extend

- **Add a data source:** create `providers/<name>/api.py` (`fetch`) + `adapter.py` (`to_hotel`),
  add fixtures if needed, then `register(ComposedProvider("<name>", <Api>(), <Adapter>()))` in
  `providers/registry.py`. Add `<name>` to `enabled_providers`. No core/pipeline changes. (See
  `providers.md`.)
- **Add a scorer:** implement the `HotelScorer` protocol; wire it in
  `scoring/__init__.py:make_scorer`. (See `scoring.md`.)
- **Add a lens:** a new pure function in `stages/lenses.py` + a `LensName` member (see
  `contract.md`) + a line in `pipeline._build_lenses`. It is a new projection over the existing
  scored set, not a new pipeline. (See `pipeline.md`.)
- **Cross-cutting helper:** put it in `utils/` (e.g. `utils/geo.py`, `utils/text.py`).
