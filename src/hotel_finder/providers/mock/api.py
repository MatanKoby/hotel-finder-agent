"""Mock provider API: loads raw hotel records from bundled JSON fixtures.

Stands in for a real data source. A real ``api.py`` would issue an HTTP request built from the
query; this one just reads a packaged fixture file and returns its records unchanged.
"""

from __future__ import annotations

import json
from importlib import resources

from hotel_finder.contracts import HotelSearchRequest
from hotel_finder.providers.base import RawRecord

_FIXTURES_PACKAGE = "hotel_finder.providers.mock.fixtures"


class MockApi:
    """Returns the raw records from a bundled fixture dataset."""

    def __init__(self, dataset: str = "barcelona") -> None:
        self._dataset = dataset

    async def fetch(self, request: HotelSearchRequest) -> list[RawRecord]:
        # A real provider would use `request` to build a network request. The mock ignores it and
        # always returns its fixture city; the pipeline's filter/area logic does the rest.
        return self._load(self._dataset)

    def _load(self, dataset: str) -> list[RawRecord]:
        text = (resources.files(_FIXTURES_PACKAGE) / f"{dataset}.json").read_text(encoding="utf-8")
        records: list[RawRecord] = json.loads(text)
        return records
