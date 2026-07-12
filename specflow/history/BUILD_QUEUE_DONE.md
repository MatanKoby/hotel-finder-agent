# Build Queue — Completed History

One-paragraph summaries of every shipped batch, newest at the top. Skim this for context when
picking a new claim. The full implementation history is in `git log` + `specflow/history/CLAIMS_DONE.md`.

<!-- Append a summary here when you finish a batch (see specflow/procedures/finish-batch.md).
     Format, e.g.:

## Batch 1 — <title>
Shipped <what> in <where>. Key commit `<sha>`. <One line on any follow-up deferred.>
-->

## Batch C1 — Contract reshape (flatten Pick, renames, trip-level guests)
Reshaped the M1 contract to the orchestrator-agreed flat/renamed wire shape (`spec/contract.md`),
no new provider data. Request gained trip-level `guests: Occupancy` + `guest_nationality`, `Stay.rooms`
became `list[Occupancy] | None` (None → one room from `guests`, else overrides), `guest_nationality`
left `Stay`. Response: `status` → `agent_status`, `meta`/`RecommendationMeta` → `diagnostics`/`Diagnostics`,
`ResolvedQuery` gained `area`. `Pick` flattened (fields promoted from `Hotel`, no nested `hotel`/`raw`/
`sources`), `subscores` → `why`, `score` bounded `[0,1]`, `image_url`/`distance_to_desired_km` declared
but `None` (→ C2). Provider `hotels_rates` now takes `rooms` + trip-level `guest_nationality`. Key commit
`9723b95`. `make check` green, 66 tests (+1: `Pick.score ∈ [0,1]` and one overall score across lenses).
Deferred: `image_url` + `distance_to_desired_km` population (Batch C2).

## Batch M1e — Integration surface + minimal orchestrator example (Milestone 1 complete)
Shipped `examples/orchestrator_sim.py` (builds a `HotelSearchRequest`, calls `search()`/`search_sync()`,
pretty-prints the envelope), finalized the top-level exports (+ `py.typed`), removed `demo.py` and its
console-script, pointed `make run` at the example, and fixed `ENABLED_PROVIDERS` env parsing (plain
comma-separated string via `NoDecode`). Rewrote `README.md` for submodule usage. Key commit `b1d06d4`.
`make check` green, 65 tests; fresh `pip install -e .` exposes the API; `make run` prints the envelope
offline and live over LiteAPI. **This completes Milestone 1 (M1a–M1e): hotel-finder is submodule-ready.**

## Batch M1d — Nebius LLM scoring (two transports) + effective-scorer reporting
Shipped two LLM transports behind a `_ChatBackend` seam in `scoring/llm.py`: OpenAI-compatible
(existing) and a new `scoring/nebius_endpoint.py` thin Ollama-REST client (model auto-discovered via
`/api/tags`, `/api/chat`, bearer, no key, cold-start retry); selected by `llm_backend`/env. Added
`ScoreReport` in `scoring/base.py` so `meta.scorer` reflects the scorer that actually ran and a
fallback surfaces as a warning. Config got `llm_backend` + `nebius_endpoint_*`. Key commit
`c843b6d`. `make check` green, 60 tests (both backends stubbed offline). Deferred: live LLM
verification (no key/endpoint configured); scoring weightings unchanged (P2).

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
