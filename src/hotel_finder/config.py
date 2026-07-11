"""Runtime configuration, loaded from environment variables and an optional ``.env`` file.

Centralizes every tunable: which providers/scorer are active, LLM endpoint details, pipeline
thresholds, and the price-band cutoffs used to derive a band from a bare price.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from hotel_finder.models import PriceBand


class Settings(BaseSettings):
    """Application settings. Field names map to upper-cased env vars (e.g. ``SCORER``)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- providers & scorer selection ---
    enabled_providers: list[str] = Field(default_factory=lambda: ["mock"])
    scorer: str = "heuristic"  # "heuristic" | "llm"

    # --- LLM scorer (OpenAI-compatible endpoint; defaults target Groq's free tier) ---
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    llm_timeout: float = 30.0

    # --- LiteAPI data source (real hotels, content, prices; see data-sources.md) ---
    liteapi_api_key: str = ""  # sandbox `sand_` key for M1; sent as the X-API-Key header
    liteapi_base_url: str = "https://api.liteapi.travel/v3.0"
    liteapi_timeout: float = 30.0

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
