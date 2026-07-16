"""Runtime configuration, loaded from environment variables and an optional ``.env`` file.

Centralizes every tunable: which providers/scorer are active, LLM endpoint details, pipeline
thresholds, and the price-band cutoffs used to derive a band from a bare price.
"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from hotel_finder.models import PriceBand


class Settings(BaseSettings):
    """Application settings. Field names map to upper-cased env vars (e.g. ``SCORER``)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- providers & scorer selection ---
    # `NoDecode` + the validator below let `ENABLED_PROVIDERS` be a plain comma-separated string
    # (e.g. `liteapi` or `mock,liteapi`) as well as a JSON list.
    enabled_providers: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["mock"])
    scorer: str = "heuristic"  # "heuristic" | "llm"

    @field_validator("enabled_providers", mode="before")
    @classmethod
    def _parse_providers(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    # --- LLM scorer (OpenAI-compatible endpoint; defaults target Groq's free tier) ---
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_timeout: float = 30.0
    # Hybrid-reasoning models (e.g. Qwen3) default to a verbose "thinking" pass that inflates
    # latency and can break the JSON scorer. Set true to disable it on the OpenAI-compatible
    # backend (sends chat_template_kwargs.enable_thinking=false); no-op on models without it.
    llm_disable_thinking: bool = False

    # Which LLM transport to use: "auto" picks `endpoint` when NEBIUS_ENDPOINT_URL is set, else
    # `openai` when LLM_API_KEY is set, else the heuristic. Force with openai/endpoint.
    llm_backend: str = "auto"  # "auto" | "openai" | "endpoint"

    # --- Nebius serverless endpoint (orchestrator run mode; Ollama REST, no API key) ---
    nebius_endpoint_url: str = ""  # shared endpoint https URL
    nebius_endpoint_token: str = ""  # bearer token
    nebius_endpoint_model: str = ""  # blank = auto-discover the single served model via /api/tags

    # --- LiteAPI data source (real hotels, content, prices; see data-sources.md) ---
    liteapi_api_key: str = ""  # sandbox `sand_` key for M1; sent as the X-API-Key header
    liteapi_base_url: str = "https://api.liteapi.travel/v3.0"
    liteapi_timeout: float = 30.0

    # --- geocoding (free-text Place resolution; free keyless Nominatim, needs a User-Agent) ---
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    geocoder_user_agent: str = "hotel-finder/0.1 (+https://github.com/MatanKoby/hotel-finder)"
    geocoder_timeout: float = 10.0
    # Geocode a structured `desired_area` into a ranking point (proximity bias +
    # distance_to_desired) even when the search itself is city-level. A soft bias, not a hard
    # filter. Offline tests set this false to stay network-free (the mock scenarios still exercise
    # the area-string fallback).
    geocode_desired_area: bool = True

    # --- pipeline thresholds ---
    min_candidates: int = 8  # below this after filtering, try the bounded-agency widening
    shortlist_size: int = 15  # how many candidates reach the scorer
    max_widen_steps: int = 3  # cap on widening retries (step 0 radius; middle steps widen the
    # price band by widen_price_factor; the final step drops price bounds to guarantee recovery)
    widen_radius_km: float = 3.0  # how much to grow the area radius per widen step
    widen_price_factor: float = 0.5  # fractional price-band widening per middle widen step

    # --- ANCHOR intent (peers of a named hotel; see pipeline.md → Anchor intent) ---
    anchor_radius_km: float = 3.0  # peers must sit within this radius of the anchor hotel
    anchor_price_low_factor: float = 0.6  # peer price floor = anchor price * this
    anchor_price_high_factor: float = 1.6  # peer price ceiling = anchor price * this
    anchor_star_tolerance: int = 1  # peers may be up to this many stars below the anchor's class
    anchor_rating_tolerance: float = 1.0  # peers may be this far below the anchor's guest score

    # --- REFINE (feedback loop; see pipeline.md → Refine) ---
    refine_radius_km: float = 3.0  # re-centre radius around the wanted centroid
    refine_price_low_factor: float = 0.7  # wanted price floor = min wanted price * this
    refine_price_high_factor: float = 1.4  # wanted price ceiling = max wanted price * this
    refine_star_tolerance: int = 1  # new options may be this many stars below the wanted floor
    refine_rating_tolerance: float = 1.0  # this far below the wanted guest-score floor
    refine_bias_weight: float = 0.15  # cap on the wanted/unwanted preference nudge to the score

    # --- price-band cutoffs (per-night, in the dominant currency; v1 mock uses EUR) ---
    band_budget_max: float = 90.0
    band_midrange_max: float = 180.0
    band_upscale_max: float = 350.0  # anything above this is LUXURY

    def price_band_for(self, price: float) -> PriceBand:
        """Bucket a per-night price into a :class:`PriceBand` using the configured cutoffs."""
        if price <= self.band_budget_max:
            return PriceBand.BUDGET
        if price <= self.band_midrange_max:
            return PriceBand.MIDRANGE
        if price <= self.band_upscale_max:
            return PriceBand.UPSCALE
        return PriceBand.LUXURY
