# Build Queue — Completed History

One-paragraph summaries of every shipped batch, newest at the top. Skim this for context when
picking a new claim. The full implementation history is in `git log` + `specflow/history/CLAIMS_DONE.md`.

<!-- Append a summary here when you finish a batch (see specflow/procedures/finish-batch.md).
     Format, e.g.:

## Batch 1 — <title>
Shipped <what> in <where>. Key commit `<sha>`. <One line on any follow-up deferred.>
-->

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
