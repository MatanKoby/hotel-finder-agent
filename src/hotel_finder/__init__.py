"""hotel-finder: a hotel-recommending agent (deterministic pipeline, pluggable providers/scorer).

The public entry point is :func:`recommend` — a structured ``HotelQuery`` in, a
``Recommendations`` out.
"""

from hotel_finder.contracts import HotelQuery, Recommendations
from hotel_finder.pipeline import recommend

__version__ = "0.1.0"
__all__ = ["HotelQuery", "Recommendations", "recommend"]
