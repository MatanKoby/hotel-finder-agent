# Scoring (`scoring/`)

The one step that wants judgment, isolated behind an interface so the rest of the system stays
deterministic and testable (see `architecture.md`). Called once by the pipeline on the shortlist
(step 7 in `pipeline.md`).

## The interface

`ScoredHotel = {hotel, score, subscores{value, location, character, gem_signal}, rationale}`.

`HotelScorer` protocol: `async def score(hotels, query) -> list[ScoredHotel]`.

**`overall_score(value, location, character) = clamp(0.5*value + 0.3*location + 0.2*character)`**
is the single source of weighting. **Both** scorers use it: the LLM provides the subscores, the
overall is computed locally for consistency.

`make_scorer(settings)` returns `LLMScorer` when `settings.scorer == "llm"`, else
`HeuristicScorer` (see `config.md`).

## `HeuristicScorer` (default, deterministic, no network)

- **value** = `0.7*(rating/10) + 0.3*affordability`, where affordability = `1 − price_norm`
  (price normalized within the shortlist's min/max; `0.5` if there is no price spread).
- **location** = `1 − dist/5km` (if `center` set), else `1.0 / 0.5` for desired-area
  match/non-match, else `0.6` neutral.
- **character** = `0.5*(len(amenities)/8) + 0.4*(stars/5) + 0.1*(has description)`.
- **gem_signal** = `rating_factor * scarcity * value`, with `rating_factor = clamp((rating−8)/2)`
  and `scarcity = clamp(1 − reviews/300)` (`0.5` if review_count unknown). The **product** means
  a gem must be highly rated **and** under-the-radar **and** a good value.
- **rationale** — a short deterministic sentence assembled from the strongest components.

## `LLMScorer` (opt-in)

Builds **one** prompt with a compact JSON of the shortlist plus query context; asks for
`{"scores":[{id, value, location, character, gem_signal, rationale}]}` (`temperature=0`);
validates with Pydantic; **one repair retry** on bad JSON. It **falls back to `HeuristicScorer`**
(and adds a `warning`, see `contract.md`) if: no LLM is configured, the LLM is unreachable, any
exception, or the response omits any hotel id. Overall is computed locally.

**Two LLM backends**, both contacted by this repo, selected by `llm_backend` / env (`config.md`):

1. **OpenAI-compatible** (eval/testing → Nebius Token Factory): the `openai` SDK against
   `llm_base_url` with `llm_api_key` + `llm_model`, `response_format=json_object`. Uncapped model
   choice.
2. **Nebius serverless endpoint** (orchestrator, no API key): a thin client over the **Ollama REST
   API** (`POST {url}/api/chat`, bearer `nebius_endpoint_token`), the single served model
   auto-discovered via `GET {url}/api/tags`. It probes `/api/tags` for liveness, retries a cold
   start briefly, then falls back to heuristic if still unreachable. Mirrors the sibling flight
   agent's `nebius_endpoint_manager.py` pattern, but as a **thin client against the shared
   endpoint** (no Nebius-CLI lifecycle).

Both back the same `HotelScorer` interface, so the pipeline is unchanged. Endpoints, keys, models,
and timeouts are all in `config.md`.

The starting weightings and thresholds here are reasonable defaults, not tuned; revisiting them
is tracked in `roadmap.md`.
