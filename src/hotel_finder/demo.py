"""Run the agent end-to-end from the command line and print the three lenses.

uv run python -m hotel_finder.demo --location Barcelona
uv run python -m hotel_finder.demo --location Barcelona --area "Barri Gotic" --scorer llm
"""

from __future__ import annotations

import argparse
import asyncio

from hotel_finder.config import Settings
from hotel_finder.contracts import HotelQuery, LensName, Recommendations
from hotel_finder.pipeline import recommend

_LENS_TITLES = {
    LensName.STRATIFIED_BEST: "Best in each price tier",
    LensName.OVERALL_STANDOUTS: "Overall standouts",
    LensName.HIDDEN_GEMS: "Hidden gems",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Recommend hotels for a location.")
    parser.add_argument("--location", default="Barcelona", help="city or area to search")
    parser.add_argument("--area", default=None, help="preferred neighborhood")
    parser.add_argument(
        "--scorer",
        choices=["heuristic", "llm"],
        default=None,
        help="override the configured scorer",
    )
    args = parser.parse_args()

    settings = Settings()
    if args.scorer is not None:
        settings = settings.model_copy(update={"scorer": args.scorer})

    query = HotelQuery(location=args.location, desired_area=args.area)
    recommendations = asyncio.run(recommend(query, settings))
    _print(recommendations)


def _print(recommendations: Recommendations) -> None:
    meta = recommendations.meta
    print(
        f"\nRecommendations  (scorer={meta.scorer}, providers={meta.providers_used}, "
        f"found={meta.candidates_found}, after_filter={meta.candidates_after_filter}, "
        f"shortlisted={meta.shortlisted}, widened={meta.widened})"
    )
    for lens, picks in recommendations.lenses.items():
        print(f"\n== {_LENS_TITLES.get(lens, lens.value)} ==")
        if not picks:
            print("  (none)")
            continue
        for pick in picks:
            hotel = pick.hotel
            band = hotel.price_band.value if hotel.price_band else "?"
            price = f"€{hotel.price_per_night:.0f}" if hotel.price_per_night is not None else "n/a"
            print(f"  • {hotel.name} [{band}, {price}] score={pick.score:.2f} — {pick.rationale}")


if __name__ == "__main__":
    main()
