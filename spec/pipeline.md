# The pipeline (`pipeline.py`) and stages (`stages/`)

The deterministic orchestrator, `search(request, settings=None)`, and the stages it drives.
These change in tandem, so they share one spec file. Plain code chooses control flow, never the
LLM: the sequence is fixed and known up front, which is what keeps the agent evaluable (see
`architecture.md`).

## Sequence

1. **Resolve** — input is a structured `HotelSearchRequest` (see `contract.md`); resolve `Place`
   (structured passthrough, or geocode `text`) into a country/city and/or `center`, recorded in
   `HotelSearchResponse.resolved`. A geocode failure warns and proceeds (M1c).
2. **Gather** — `asyncio.gather(*providers.search(query), return_exceptions=True)`. A provider
   that errors is **logged and skipped**, never fatal. (Providers: `providers.md`.)
3. **Merge + dedupe** (`stages/dedupe.py`) — same hotel from different providers collapsed.
4. **Derive price bands** — `_with_price_band`: backfill a missing `price_band` from
   `price_per_night` via `Settings.price_band_for()` (cutoffs in `config.md`).
5. **Hard filter + bounded-agency widening** (`stages/filtering.py` + `_filter_with_widening`) —
   build `FilterCriteria` from the query; if survivors are `< min_candidates`, relax soft
   constraints with a **capped retry**. Sets `meta.widened`. Detail below.
6. **Shortlist** (`stages/shortlist.py`) — cheap deterministic pre-rank, keep top
   `shortlist_size`.
7. **Score once** (`scoring/`) — `make_scorer(settings).score(shortlist, query)`. The single
   expensive step (see `scoring.md`).
8. **Lenses** (`stages/lenses.py`) — project the one scored set three ways.
9. **Explain** (`stages/explain.py`) — `ScoredHotel → Pick` (+ coordinates, offers) → `HotelSearchResponse`.

## Dedupe (`stages/dedupe.py`)

Two records are the same hotel when `normalize_text(name)` is equal **and** (if both have
coords) they are within **150 m** (`haversine`). Merge keeps the **primary** (first-seen)
identity, coalesces missing optional fields from the other (primary preferred), **unions
amenities**, and **unions `sources`**.

## Filter + widening (`stages/filtering.py`)

`FilterCriteria(must_have_amenities, price_min, price_max, center, radius_km)`. A hotel passes
iff: it has all must-have amenities; its price (if a bound is set) is within range (**unknown
price is excluded when a bound is set**); and (if `center` + `radius_km` given) it is within
radius (hotels without coords excluded).

Widening (`_filter_with_widening`): if survivors are below `min_candidates`, relax **soft**
constraints with a capped retry (step 0: grow area radius; step 1: drop price bounds). Must-have
amenities are **never** relaxed. This is a fixed `if` + cap, not the LLM deciding, which
preserves evaluability. Caps and radius come from `config.md`.

**Budget fallback.** When it is the price-bound relaxation that brought candidates back (nothing
fit `price_max`), those hotels are the budget-too-low fallback from `contract.md` → Budget and
offers: their offers are flagged `over_budget = True`, `status` becomes `degraded`, and a
`warning` records the price floor. Within budget, over-budget hotels are not returned at all.

## Shortlist (`stages/shortlist.py`)

Cheap score = `rating/10` + review-confidence (`min(reviews/500, 1) * 0.2`) − distance penalty
(`min(dist/5km, 1) * 0.3`, only if `center` set) + **0.2 desired-area bonus** (if
`normalize_text(desired_area) in normalize_text(area)`). Sorted descending, **id tie-break** for
determinism, truncated to `size`.

## Lenses (`stages/lenses.py`)

Pure functions over `list[ScoredHotel]` (`LensName` members in `contract.md`):

- `stratified_best(scored, per_band=1)` — top `per_band` from each band, emitted in fixed
  budget→luxury order (absent bands skipped). The pipeline calls it with `per_band=1` (top of
  each tier → budget coverage).
- `overall_standouts(scored, k)` — top `k` by overall score (tiers ignored).
- `hidden_gems(scored, k, min_gem=0.4)` — hotels with `gem_signal >= 0.4`, sorted by gem signal.

## Explain (`stages/explain.py`)

`to_pick` copies score/subscores/rationale, sets `coordinates = hotel.location`, and attaches the
hotel's `offers` (cheapest refundable + cheapest non-refundable, per `contract.md` → Budget and
offers), producing the `Pick` objects that fill `HotelSearchResponse.lenses`. The pipeline also
sets `status`, `warnings`, `resolved`, and `meta` on the response.
