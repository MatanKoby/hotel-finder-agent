"""The single (heuristic-or-LLM) scoring step. ``make_scorer`` picks one from settings."""

from __future__ import annotations

from hotel_finder.config import Settings
from hotel_finder.scoring.base import HotelScorer, ScoredHotel, overall_score
from hotel_finder.scoring.heuristic import HeuristicScorer
from hotel_finder.scoring.llm import LLMScorer

__all__ = [
    "HeuristicScorer",
    "HotelScorer",
    "LLMScorer",
    "ScoredHotel",
    "make_scorer",
    "overall_score",
]


def make_scorer(settings: Settings) -> HotelScorer:
    """Return the scorer selected by ``settings.scorer`` ("heuristic" by default)."""
    if settings.scorer == "llm":
        return LLMScorer(settings)
    return HeuristicScorer()
