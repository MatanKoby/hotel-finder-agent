"""The scoring interface — the single seam where (optional) LLM judgment enters the pipeline.

A scorer takes the shortlist and rates each hotel on the fuzzy axes, exactly once per request.
``overall_score`` defines how the per-axis subscores combine into the headline score; both the
heuristic and the LLM scorer use it so the downstream lens logic stays consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from hotel_finder.context import SearchContext
from hotel_finder.models import Hotel


class ScoredHotel(BaseModel):
    """A hotel plus its scores. ``subscores`` carries value/location/character/gem_signal."""

    model_config = ConfigDict(extra="forbid")

    hotel: Hotel
    score: float  # overall, 0..1
    subscores: dict[str, float] = Field(default_factory=dict)
    rationale: str = ""


@dataclass(frozen=True)
class ScoreReport:
    """What a scorer **actually** did on its last run, so the pipeline can report the effective
    scorer and surface a fallback as a warning (see ``contract.md`` → ``meta.scorer``)."""

    scorer: str  # "heuristic" | "llm"
    warnings: list[str] = field(default_factory=list)


class HotelScorer(Protocol):
    """Scores a shortlist on the fuzzy axes. Called exactly once per request."""

    @property
    def report(self) -> ScoreReport:
        """The effective-scorer report from the most recent :meth:`score` call."""
        ...

    async def score(self, hotels: list[Hotel], context: SearchContext) -> list[ScoredHotel]: ...


def overall_score(value: float, location: float, character: float) -> float:
    """Combine the per-axis subscores into the headline score (single source of weighting)."""
    return max(0.0, min(1.0, 0.5 * value + 0.3 * location + 0.2 * character))
