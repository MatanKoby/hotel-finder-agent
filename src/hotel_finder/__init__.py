"""hotel-finder: a hotel-recommending agent (deterministic pipeline, pluggable providers/scorer).

Importable as a git submodule. The public entry point is :func:`search` (async) with a thin
:func:`search_sync` wrapper — a structured ``HotelSearchRequest`` in, a ``HotelSearchResponse``
envelope out. Construct ``HotelSearchRequest`` on the caller's side to validate input before
calling (the Pydantic models are the shared validator).
"""

from hotel_finder.config import Settings
from hotel_finder.contracts import (
    Diagnostics,
    Filters,
    HotelFeedback,
    HotelFeedbackAttributes,
    HotelRefineRequest,
    HotelSearchRequest,
    HotelSearchResponse,
    Intent,
    LensName,
    Occupancy,
    Pick,
    Place,
    RateOffer,
    ResolvedQuery,
    Stay,
)
from hotel_finder.models import Amenity, GeoPoint, Hotel, PriceBand
from hotel_finder.pipeline import refine, refine_sync, search, search_sync

__version__ = "0.1.0"
__all__ = [
    "Amenity",
    "Diagnostics",
    "Filters",
    "GeoPoint",
    "Hotel",
    "HotelFeedback",
    "HotelFeedbackAttributes",
    "HotelRefineRequest",
    "HotelSearchRequest",
    "HotelSearchResponse",
    "Intent",
    "LensName",
    "Occupancy",
    "Pick",
    "Place",
    "PriceBand",
    "RateOffer",
    "ResolvedQuery",
    "Settings",
    "Stay",
    "refine",
    "refine_sync",
    "search",
    "search_sync",
]
