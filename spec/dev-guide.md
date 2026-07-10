# Dev guide: running, testing, tooling, extending

How to run the agent, the tooling contract, and where the extension points are. The design each
of these touches lives in the concern files linked below.

## Running and testing

```bash
make install            # uv sync (creates .venv, installs runtime + dev deps)
make run                # demo on bundled mock data (offline, $0)
make check              # ruff + mypy + pytest
# or:
uv run python -m hotel_finder.demo --location Barcelona [--area "Barri Gotic"] [--scorer heuristic|llm]
uv run pytest
```

**Enable the LLM scorer:** copy `.env.example` → `.env`, set `LLM_API_KEY` + `LLM_MODEL`, run
with `--scorer llm` (or `SCORER=llm`). With no key it logs a warning and uses the heuristic (see
`scoring.md`, `config.md`).

## Tooling

`uv` manages deps and the venv. Runtime deps: `pydantic`, `pydantic-settings`, `openai`. Dev
deps: `pytest`, `pytest-asyncio`, `ruff`, `mypy` (all in `pyproject.toml`).

- **ruff** lint + format (line length 100; rules E, F, I, UP, B, SIM).
- **mypy** `strict`, scoped to `src` (tests use untyped doubles), pydantic plugin enabled.
- **pytest** `asyncio_mode=auto` (async tests need no decorator). 26 tests, fully offline (the
  LLM path uses a stubbed client).
- `Makefile` targets: `install / lint / format / typecheck / test / check / run`.
- Public entry re-exported: `from hotel_finder import recommend`.

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
