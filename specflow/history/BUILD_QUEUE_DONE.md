# Build Queue — Completed History

One-paragraph summaries of every shipped batch, newest at the top. Skim this for context when
picking a new claim. The full implementation history is in `git log` + `specflow/history/CLAIMS_DONE.md`.

<!-- Append a summary here when you finish a batch (see specflow/procedures/finish-batch.md).
     Format, e.g.:

## Batch 1 — <title>
Shipped <what> in <where>. Key commit `<sha>`. <One line on any follow-up deferred.>
-->

## Batch P7 — Refinement entry point (feedback loop)
Added a second stable entry point `refine()` / `refine_sync()` parallel to `search` (same
`HotelSearchResponse` out), for the orchestrator's two-call loop: `search`, then `refine` with the
user's wanted / unwanted marks on the prior response. New stable `Pick.id` (`"{source}:{id}"`) is the
search→refine identity the orchestrator echoes back. New `stages/refine.py`: `match_feedback` (id then
name), `plan_refine` (exclude `wanted ∪ unwanted ∪ exclude` so only **new** options return, a wanted
`RefineEnvelope` that tightens price/star/rating + re-centres on the wanted centroid, and
`apply_preference`, a bounded post-scoring nudge over area/band/star/amenities surfaced as
`why["preference"]`). The agent stays stateless: `refine()` re-discovers candidates each call and
hoards nothing. `pipeline.py` extracted a shared `_assemble`/`_discover` tail so both entries build
one way; `SearchContext.preference` feeds the LLM prompt; 6 `refine_*` config knobs. Key commit
`8775700` (spec `e7d269b`, `d896524`). `make check` green (136 tests, +17). Live LLM path unverified
(Nebius creds unset); validate via `make eval` when configured.

## Batch P3 — ANCHOR intent (peers of a named hotel)
Implemented the reserved `anchor` intent: `intent=anchor` + `anchor_hotel` finds **peers of a named
hotel**. New `stages/anchor.py` — `find_anchor` locates the anchor among the discovered candidates by
normalized name (exact, else unique containment), and `anchor_envelope` derives a peer envelope
(proximity via anchor coords + `anchor_radius_km`, a price window `anchor_price_low/high_factor`, and
star/rating class floors); `to_criteria` folds it into the request's `Filters` so it only tightens.
The pipeline (`_apply_anchor`, run between price-band derivation and the hard filter) excludes the
anchor, applies the envelope through the normal widening + scoring, and re-centres ranking on the
anchor (`resolved.center` = anchor location, so proximity + `distance_to_desired_km` measure from it).
Anchor not found / too thin → warning + degraded + broad zone fallback (never crashes). A contract
validator requires a non-empty `anchor_hotel` when `intent=anchor`; 5 `anchor_*` config knobs added.
Key commits `e69c049` (code) + `a125f75` (spec). `make check` green, 119 tests (+14). Follow-ups
deferred: anchor-aware rationale phrasing in `explain.py`; the `anchor_*` factors left untuned.

## Batch P2 — Result-quality improvements
Addressed the P1/P6 live-eval findings (`spec/roadmap.md` items 1-5). `stratified_best`
(`stages/lenses.py`) falls back to **star tiers** when no candidate has a price band, so a
content-only search (no rates) still fills the lens. `_resolve` (`pipeline.py`) now separates the
**filter centre** from a **desired point** (the filter centre, else a geocoded `desired_area`), a
soft ranking bias (not a hard radius) that drives proximity ranking + `distance_to_desired_km` for
area-string searches — new `Settings.geocode_desired_area` (off in offline eval for hermetic tests).
The heuristic name-only `location` is graded (exact/partial-word/different) not flat; the LLM payload
carries `coordinates` + `distance_to_desired_km` + `in_desired_area` and the prompt scores from them.
The "few reviews" gem rationale is gated on a known-low `review_count`, the LLM is told not to
gem-label well-reviewed hotels, and rationales are lens-aware (`stages/explain.py`). Price widening is
now gentle (middle steps widen the band by `widen_price_factor`, only the final step drops the
bounds; `max_widen_steps` 2→3). Key commits `fb83c93` (code) + `85eb32b` (spec). `make check` green,
105 tests (+15). Verified live (LiteAPI + Qwen3-32B): content-only fills stratified_best via star
tiers; LLM `location` tracks distance instead of a flat 1.00. Open: finding 6 (semantic eval);
untuned weightings/cutoffs left deliberately until that ground truth exists.

## Batch P6 — Live-eval wiring + LLM thinking-off toggle
Made `make eval` real-config-aware and reached the closest-to-orchestrator LLM. `tests/eval/report.py`
now reads `Settings()` from the environment / `.env` (was pinned offline) so the catalog runs live
(real LiteAPI + LLM); tests stay hermetic-offline. Added a per-scenario scorer column so an
LLM→heuristic fallback is visible. Added `Settings.llm_disable_thinking`, wired into the
OpenAI-compatible backend as `extra_body={"chat_template_kwargs":{"enable_thinking":false}}`, so
`Qwen/Qwen3-32B` (Token Factory's closest dense-32B to the orchestrator's non-thinking `qwen2.5-32b`)
runs fast and returns clean JSON instead of timing out. `.env.example` → Qwen3-32B +
`LLM_DISABLE_THINKING=true`; spec updated (`config.md`, `scoring.md`, `dev-guide.md`). Key commit
`f22fdf9`. `make check` green, 92 tests (+2). Verified live: all 8 scenarios scored by `scorer=llm`,
0 fallbacks, invariants pass against real LiteAPI + Nebius Token Factory. Deferred: cosmetic httpx
"event loop closed" teardown trace; no thinking-off knob on the serverless-endpoint backend yet.

## Batch P1 — Evaluation harness and test scenarios
Shipped a result-quality evaluation harness in `tests/eval/`: `scenarios.py` (an 8-scenario catalog
of `HotelSearchRequest` + declarative `Expect`, provider-agnostic), `metrics.py`
(`check_invariants()` = contract guarantees for any request/provider + `evaluate()` = countable
signals), `test_eval_scenarios.py` (runs under `make check`), and `report.py` (`make eval`, baseline
metrics table, non-zero exit on any invariant breach). Scenarios cover budget-ok, over-budget
fallback, refundable true/false, content-only, thin-result widening, geo-centre — all offline on the
mock provider + heuristic scorer, deterministic and free. Documented in `spec/dev-guide.md`. Key
commit `a77c522`. `make check` green, 90 tests (+17). The baseline Batch P2 tunes against; it also
surfaced two mock content gaps (0% image_url, 0 non-refundable offers) that LiteAPI fills. No
follow-ups deferred.

## Batch C2 — Provider-backed enrichment (image_url, distance_to_desired_km)
Populated the two `Pick` fields C1 left nullable, completing the reshape. Added `Hotel.image_url`
(`models.py`); the LiteAPI adapter maps `main_photo`→`thumbnail` fallback (kept in `raw`;
`data-sources.md` mapping updated), mock leaves it `None`, `explain.py` surfaces it. `explain.to_pick`/
`to_picks` take the resolved `center` and compute `distance_to_desired_km` = haversine(hotel, center)
(2 dp, `None` when center or coords missing); the pipeline threads `resolved.center` through
`_build_lenses`. `review_count`/`description` confirmed end-to-end. Key commit `38ae7d4`. `make check`
green, 73 tests (+7); verified live over the LiteAPI sandbox (real photo URLs + 0.4-1.4 km distances
from a Sagrada Família center). Deferred: distance is to `resolved.center`, not a geocoded
`desired_area` point.

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
