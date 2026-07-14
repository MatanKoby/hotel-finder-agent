# Configuration (`config.py`, `Settings`)

pydantic-settings `BaseSettings`, reads env plus `.env`. Each field maps to its upper-cased env
var. These knobs drive the pipeline (`pipeline.md`), the scorer selection (`scoring.md`), and
the provider set (`providers.md`).

| Setting | Default | Env |
|---|---|---|
| `enabled_providers` | `["mock"]` | `ENABLED_PROVIDERS` |
| `scorer` | `"heuristic"` | `SCORER` |
| `llm_base_url` | `https://api.groq.com/openai/v1` | `LLM_BASE_URL` |
| `llm_api_key` | `""` | `LLM_API_KEY` |
| `llm_model` | `llama-3.3-70b-versatile` (verify current id at console.groq.com) | `LLM_MODEL` |
| `llm_timeout` | `30.0` | `LLM_TIMEOUT` |
| `llm_backend` | `auto` (else `openai` / `endpoint`) | `LLM_BACKEND` |
| `llm_disable_thinking` | `false` (disable a hybrid model's thinking pass; OpenAI backend) | `LLM_DISABLE_THINKING` |
| `nebius_endpoint_url` | `""` (orchestrator serverless endpoint) | `NEBIUS_ENDPOINT_URL` |
| `nebius_endpoint_token` | `""` (bearer) | `NEBIUS_ENDPOINT_TOKEN` |
| `nebius_endpoint_model` | `""` (auto-discovered via `/api/tags`) | `NEBIUS_ENDPOINT_MODEL` |
| `liteapi_api_key` | `""` | `LITEAPI_API_KEY` |
| `liteapi_base_url` | `https://api.liteapi.travel/v3.0` | `LITEAPI_BASE_URL` |
| `geocode_desired_area` | `true` (geocode `desired_area` into a ranking point; off in offline tests) | `GEOCODE_DESIRED_AREA` |
| `min_candidates` | `8` | `MIN_CANDIDATES` |
| `shortlist_size` | `15` | `SHORTLIST_SIZE` |
| `max_widen_steps` | `3` | `MAX_WIDEN_STEPS` |
| `widen_radius_km` | `3.0` | `WIDEN_RADIUS_KM` |
| `widen_price_factor` | `0.5` (fractional price-band widening per middle widen step) | `WIDEN_PRICE_FACTOR` |
| `band_budget_max` / `band_midrange_max` / `band_upscale_max` | `90 / 180 / 350` (EUR/night) | resp. |

## LLM run modes (Nebius)

Two ways to reach the LLM, **both contacted by this repo itself**, selected by `llm_backend`
(`auto` picks `endpoint` when `NEBIUS_ENDPOINT_URL` is set, else `openai` when `LLM_API_KEY` is
set, else heuristic). See `scoring.md`.

- **Eval / testing (this repo): OpenAI-compatible + API key → Nebius Token Factory.** Set
  `SCORER=llm`, `LLM_BASE_URL=https://api.tokenfactory.nebius.com/v1/`, `LLM_API_KEY=<Bearer key>`,
  `LLM_MODEL=<a chat model id from your Nebius console>`. Uncapped model choice. (The hard-coded
  defaults above point at Groq and are overridden by these values.) Token Factory has no
  `qwen2.5-32b`; the closest to the orchestrator's dense-32B endpoint is `Qwen/Qwen3-32B` with
  `LLM_DISABLE_THINKING=true` (Qwen3's thinking pass otherwise times out on the scorer prompt, and
  disabling it also matches the non-thinking `qwen2.5-32b`). `llm_disable_thinking` sends
  `chat_template_kwargs.enable_thinking=false` on the OpenAI backend; it is a no-op on models
  without a thinking mode (see `scoring.md`).
- **Orchestrator: shared Nebius serverless endpoint (no API key).** Set `SCORER=llm`,
  `NEBIUS_ENDPOINT_URL=<shared endpoint https URL>`, `NEBIUS_ENDPOINT_TOKEN=<bearer>`. The model is
  the single one the endpoint serves, auto-discovered via `GET {url}/api/tags` (override with
  `NEBIUS_ENDPOINT_MODEL`). This speaks the Ollama REST API, not OpenAI.

If neither is configured, or the LLM is unreachable, scoring falls back to the heuristic with a
warning.

## LiteAPI (data source)

`LITEAPI_API_KEY` (a sandbox `sand_` key for M1) is sent as the `X-API-Key` header against
`LITEAPI_BASE_URL`. See `data-sources.md` and `providers.md`.

## Price bands

`price_band_for(price)` buckets a price into a `PriceBand` (see `domain-model.md`) using the
`band_*_max` cutoffs (above `band_upscale_max` ⇒ luxury). This is the global band-derivation
policy the pipeline applies in step 4; adapters do not derive bands.

The price-band cutoffs (and the pipeline thresholds above) are reasonable starting values, not
tuned; revisiting them is tracked in `roadmap.md`.
