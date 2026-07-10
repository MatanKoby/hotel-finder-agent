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
| `min_candidates` | `8` | `MIN_CANDIDATES` |
| `shortlist_size` | `15` | `SHORTLIST_SIZE` |
| `max_widen_steps` | `2` | `MAX_WIDEN_STEPS` |
| `widen_radius_km` | `3.0` | `WIDEN_RADIUS_KM` |
| `band_budget_max` / `band_midrange_max` / `band_upscale_max` | `90 / 180 / 350` (EUR/night) | resp. |

**LLM endpoint for this project: Nebius Token Factory** (see `scoring.md`). Set
`LLM_BASE_URL=https://api.tokenfactory.nebius.com/v1/`, `LLM_API_KEY=<your Bearer key>`,
`LLM_MODEL=<a chat model id from your Nebius console, e.g. a Llama or Qwen instruct model>`, and
`SCORER=llm`. Nebius is OpenAI-compatible, so the existing scorer needs no code change; the
hard-coded defaults above still point at Groq and are overridden by these env values.

## Price bands

`price_band_for(price)` buckets a price into a `PriceBand` (see `domain-model.md`) using the
`band_*_max` cutoffs (above `band_upscale_max` ⇒ luxury). This is the global band-derivation
policy the pipeline applies in step 4; adapters do not derive bands.

The price-band cutoffs (and the pipeline thresholds above) are reasonable starting values, not
tuned; revisiting them is tracked in `roadmap.md`.
