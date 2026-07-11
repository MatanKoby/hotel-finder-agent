# Build Queue — Completed History

One-paragraph summaries of every shipped batch, newest at the top. Skim this for context when
picking a new claim. The full implementation history is in `git log` + `specflow/history/CLAIMS_DONE.md`.

<!-- Append a summary here when you finish a batch (see specflow/procedures/finish-batch.md).
     Format, e.g.:

## Batch 1 — <title>
Shipped <what> in <where>. Key commit `<sha>`. <One line on any follow-up deferred.>
-->

## Batch M1c — Place resolution (structured passthrough + text geocoding)
Shipped `utils/geocode.py` (a `Geocoder` protocol + keyless OSM `NominatimGeocoder` + `GeoResult` +
`make_geocoder`). The pipeline's `_resolve` is now async: a text-only `Place` is geocoded into
center+city+country_code, filling `ResolvedQuery` and an effective request the providers discover
against; structured places skip it; failures warn and proceed. Config got the Nominatim knobs. Key
commit `8aa7f36`. `make check` green, 53 tests; verified live (Nominatim: Barcelona, Tokyo). Deferred:
LiteAPI place-lookup backend (Nominatim-only for now, behind the interface).

## Batch M1b — LiteAPI provider (real hotels, content, and prices)
Shipped `providers/liteapi/` (`api.py` httpx client for `data/hotels` + `hotels/rates`, `adapter.py`
mapping to `Hotel` + cheapest refundable/non-refundable offers per `spec/data-sources.md`,
`provider.py` two-call join) plus a shipped `facilities.json` id→amenity dict and `utils.strip_html`.
Registry moved to provider factories (`Settings -> HotelProvider`); `pipeline._offers_for` reads
provider offers from `hotel.raw["offers"]`. Disabled by default. Key commit `00247df`. `make check`
green, 47 tests; verified live against the LiteAPI sandbox (50 real Barcelona hotels + rates).
Deferred: `filters.property_types` narrowing (needs a `hotelTypeId`→label dict).

## Batch M1a — Contract + the submodule search API
Shipped the submodule request/response surface (`spec/contract.md`): `HotelSearchRequest`
(`Place`/`Occupancy`/`Stay`/`Filters`, `extra="forbid"`, validators) in, a `HotelSearchResponse`
envelope out, with `RateOffer`/`ResolvedQuery` and `Pick.offers`. `pipeline.py` now exposes
`async search()` + thin `search_sync()` producing the envelope (`status` ok/empty/degraded,
`warnings`, `resolved`, budget-too-low fallback); provider failures degrade instead of crashing.
Added internal `context.py:SearchContext`, wired `min_star`/`min_guest_rating` filtering, and
folded in the specced guest-rating rescale to 0-10 (domain + heuristic + shortlist + mock
fixtures). Key commit `518dd45`. `make check` green, 40 tests. Deferred to M1e: no-mandatory-`.env`,
`py.typed`, `examples/orchestrator_sim.py`, demo.py removal. Real rates/refundability land in M1b.
