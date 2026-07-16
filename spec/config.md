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
| `anchor_radius_km` | `3.0` (ANCHOR: peers within this radius of the anchor) | `ANCHOR_RADIUS_KM` |
| `anchor_price_low_factor` / `anchor_price_high_factor` | `0.6 / 1.6` (ANCHOR: peer price window = anchor price × these) | resp. |
| `anchor_star_tolerance` | `1` (ANCHOR: peers may be this many stars below the anchor) | `ANCHOR_STAR_TOLERANCE` |
| `anchor_rating_tolerance` | `1.0` (ANCHOR: peers may be this far below the anchor's guest score) | `ANCHOR_RATING_TOLERANCE` |
| `refine_radius_km` | `3.0` (REFINE: re-centre radius around the wanted centroid) | `REFINE_RADIUS_KM` |
| `refine_price_low_factor` / `refine_price_high_factor` | `0.7 / 1.4` (REFINE: wanted price window = min/max wanted price × these) | resp. |
| `refine_star_tolerance` | `1` (REFINE: new options may be this many stars below the wanted floor) | `REFINE_STAR_TOLERANCE` |
| `refine_rating_tolerance` | `1.0` (REFINE: this far below the wanted guest-score floor) | `REFINE_RATING_TOLERANCE` |
| `refine_bias_weight` | `0.15` (REFINE: cap on the wanted/unwanted preference nudge to the overall score) | `REFINE_BIAS_WEIGHT` |
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

## Anchor intent knobs

The `anchor_*` settings shape the peer envelope for `intent = anchor`; their exact roles (proximity,
price window, class floors, and how they intersect the request's own filters) live in
`pipeline.md` → Anchor intent. Like the rest, they are starting values, not tuned.

## Refine knobs

The `refine_*` settings shape the feedback loop (`refine()`, see `contract.md` → Refinement): the
`refine_radius_km` / `refine_price_*_factor` / `refine_*_tolerance` knobs build the wanted envelope
(a multi-hotel analogue of the anchor envelope), and `refine_bias_weight` caps the post-scoring
preference nudge toward wanted / away from unwanted attributes. Their exact roles live in
`pipeline.md` → Refine. Starting values, not tuned.
