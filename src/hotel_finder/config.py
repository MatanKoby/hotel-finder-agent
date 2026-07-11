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

    # --- pipeline thresholds ---
    min_candidates: int = 8  # below this after filtering, try the bounded-agency widening
    shortlist_size: int = 15  # how many candidates reach the scorer
    max_widen_steps: int = 2  # cap on widening retries
    widen_radius_km: float = 3.0  # how much to grow the area radius per widen step

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
