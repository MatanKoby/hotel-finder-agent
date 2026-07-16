# The pipeline (`pipeline.py`) and stages (`stages/`)

The deterministic orchestrator, `search(request, settings=None)`, and the stages it drives.
These change in tandem, so they share one spec file. Plain code chooses control flow, never the
LLM: the sequence is fixed and known up front, which is what keeps the agent evaluable (see
`architecture.md`).

## Sequence

1. **Resolve** — input is a structured `HotelSearchRequest` (see `contract.md`); resolve `Place`
   (structured passthrough, or geocode `text`) into a country/city and/or `center`, recorded in
   `HotelSearchResponse.resolved`. A geocode failure warns and proceeds (M1c). Two distinct centres
   fall out: the **filter centre** (explicit `place.center` or geocoded free text) bounds the hard
   radius filter and provider discovery; the **desired point** — the filter centre, or else a
   geocoded `desired_area` (`geocode_desired_area`, `config.md`) — is what ranking and
   `distance_to_desired_km` measure against. A geocoded neighbourhood is a **soft ranking bias**,
   never a hard radius (so a miss is silent, not a warning), and becomes `resolved.center`.
2. **Gather** — `asyncio.gather(*providers.search(query), return_exceptions=True)`. A provider
   that errors is **logged and skipped**, never fatal. (Providers: `providers.md`.)
3. **Merge + dedupe** (`stages/dedupe.py`) — same hotel from different providers collapsed.
4. **Derive price bands** — `_with_price_band`: backfill a missing `price_band` from
   `price_per_night` via `Settings.price_band_for()` (cutoffs in `config.md`).
5. **Hard filter + bounded-agency widening** (`stages/filtering.py` + `_filter_with_widening`) —
   build `FilterCriteria` from the query; if survivors are `< min_candidates`, relax soft
   constraints with a **capped retry**. Sets `diagnostics.widened`. Detail below.
6. **Shortlist** (`stages/shortlist.py`) — cheap deterministic pre-rank, keep top
   `shortlist_size`.
7. **Score once** (`scoring/`) — `make_scorer(settings).score(shortlist, query)`. The single
   expensive step (see `scoring.md`).
8. **Lenses** (`stages/lenses.py`) — project the one scored set three ways.
9. **Explain** (`stages/explain.py`) — `ScoredHotel → Pick` (+ coordinates, offers) → `HotelSearchResponse`.

`intent = anchor` (see `contract.md`) inserts a **peer-resolution** step between 4 and 5 that
constrains the search to peers of a named hotel — see Anchor intent below. Everything else is
unchanged; `intent = zone` (the default) skips it.

The **`refine()`** entry point (see `contract.md` → Refinement) runs this same sequence over the
`base` trip, inserting a **feedback-resolution** step in the same slot (between 4 and 5) and a
**preference bias** after scoring (7) — see Refine below.

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
constraints with a capped retry. Every step grows the area radius; on price it is **gentle** — step
0 keeps the bounds, middle steps widen the price band by `widen_price_factor` (a slightly-too-low
budget then recovers with hotels near it, not the whole city), and only the **final** step drops
the price bounds entirely, guaranteeing the budget-too-low fallback still returns something.
Must-have amenities and quality bounds (`min_star` / `min_guest_rating`) are **never** relaxed. This
is a fixed loop + cap, not the LLM deciding, which preserves evaluability. Caps, radius, and the
price factor come from `config.md`.

**Budget fallback.** When it is the price-bound relaxation that brought candidates back (nothing
fit `price_max`), those hotels are the budget-too-low fallback from `contract.md` → Budget and
offers: their offers are flagged `over_budget = True`, `agent_status` becomes `degraded`, and a
`warning` records the price floor. Within budget, over-budget hotels are not returned at all.

## Anchor intent (`stages/anchor.py`)

`intent = anchor` (with `anchor_hotel`, see `contract.md`) searches for **peers of a named hotel**
instead of a broad area. The request still carries a `place` (the anchor's city/area), so the
pipeline discovers the usual candidate set first (steps 2–4), then, before the hard filter:

1. **Locate** the anchor among the candidates by normalized name (`find_anchor`): an exact match
   wins, else a **unique** containment match (either direction, so "Hotel Arts" finds "Hotel Arts
   Barcelona"). An ambiguous or absent match falls back (below).
2. **Derive a peer envelope** (`anchor_envelope`) from the anchor: proximity (its coords +
   `anchor_radius_km`), a price window around its price (`anchor_price_low_factor` ..
   `anchor_price_high_factor`), and star / guest-rating floors near its class (`anchor_star_tolerance`
   / `anchor_rating_tolerance`). Cutoffs are in `config.md`; a missing anchor attribute drops just
   that dimension.
3. The envelope only ever **tightens** the request's own `Filters` (the stricter bound wins; must-have
   amenities pass through) and becomes the filter base for the widening step. The anchor is
   **excluded** from the results (it is the reference, not a recommendation), and ranking re-centres
   on it: the anchor's location becomes `resolved.center`, so the shortlist proximity bias and
   `distance_to_desired_km` measure distance **from the anchor**.

**Fallback (never crash).** If the anchor can't be found, or is too thin to constrain peers (no
coords/price/star/rating), the pipeline adds a `warning`, sets `agent_status = degraded`, and runs a
broad **zone** search over the same candidates — a degenerate outcome is data the orchestrator reads,
not an exception (`contract.md` → Error philosophy).

## Refine (`stages/refine.py`)

`refine(HotelRefineRequest)` (see `contract.md` → Refinement) is the feedback loop: the same
sequence over `request.base`, with the wanted/unwanted/exclude feedback applied. Because the agent
is **stateless**, it re-discovers the candidate set from `base` (steps 1–4), then, before the hard
filter:

1. **Resolve feedback to candidates** (`resolve_feedback`): match each `HotelFeedback` to a
   re-discovered candidate by `Pick.id` (`"{source}:{id}"`) first, then by normalized name (the
   `find_anchor` matcher, so a fuzzy name still lands). A feedback item that matches no current
   candidate is not dropped: its echoed `attributes` still feed the attribute bias below.
2. **Exclude the already-seen** (`exclusion_ids`): drop the union of resolved `wanted`, `unwanted`,
   and `exclude` ids from the candidates, so refine returns **new** options rather than the same
   list re-ranked (a rejected hotel never comes back; a liked one is the seed for peers, not a
   repeat). Stateless by construction: the exclusion set is rebuilt from the request each call, not
   remembered.
3. **Derive a wanted envelope** (`refine_envelope`) from the resolved `wanted` hotels: a price
   window spanning their prices (widened by `refine_price_low_factor` / `refine_price_high_factor`),
   a star / guest-rating floor near the group's minimum (`refine_star_tolerance` /
   `refine_rating_tolerance`), the amenities they **all** share as must-haves, and a re-centre on the
   wanted **centroid** (`refine_radius_km`). Like the anchor envelope it only ever **tightens** the
   request's own `Filters` (stricter bound wins) and feeds the widening step, so a too-narrow
   envelope still recovers candidates rather than returning nothing. Empty `wanted` yields an empty
   envelope (no tightening, no re-centre).
4. **Preference bias after scoring** (`apply_preference`): a bounded nudge to each hotel's overall
   score, `+` for similarity to the `wanted` attribute profile and `−` for similarity to the
   `unwanted` one (shared area, price band, star tier, amenities, property type), capped at
   `refine_bias_weight` and re-clamped to `[0, 1]`, surfaced as `why["preference"]`. Applied to
   **whatever scorer ran** (heuristic or LLM), so the bias is deterministic and testable on the
   offline path. The LLM scorer additionally receives the wanted/unwanted profiles and any
   `reason` text as prompt context (see `scoring.md`), so live rationales stay coherent.

`diagnostics.refined = True` and `diagnostics.round` echoes `request.round`. Everything downstream
(lenses, offers, budget fallback, status) is the zone path unchanged. Degenerate cases never crash
(`contract.md` → Error philosophy): no usable feedback degrades to a plain re-search of `base`.

## Shortlist (`stages/shortlist.py`)

Cheap score = `rating/10` + review-confidence (`min(reviews/500, 1) * 0.2`) − distance penalty
(`min(dist/5km, 1) * 0.3`, only if `center` set) + **0.2 desired-area bonus** (if
`normalize_text(desired_area) in normalize_text(area)`). Sorted descending, **id tie-break** for
determinism, truncated to `size`.

## Lenses (`stages/lenses.py`)

Pure functions over `list[ScoredHotel]` (`LensName` members in `contract.md`):

- `stratified_best(scored, per_band=1)` — top `per_band` from each band, emitted in fixed
  budget→luxury order (absent bands skipped). The pipeline calls it with `per_band=1` (top of
  each tier → budget coverage). When **no** candidate has a price band (a content-only search with
  no live rates), it falls back to stratifying by **star tier** (highest first, capped to the band
  count so the pick cap holds), and to top-overall if even stars are missing, so the lens still
  fills (P1/P6 finding 1).
- `overall_standouts(scored, k)` — top `k` by overall score (tiers ignored).
- `hidden_gems(scored, k, min_gem=0.4)` — hotels with `gem_signal >= 0.4`, sorted by gem signal.
  Can be empty on real data (popular-city hotels are well-reviewed, so few clear the gem bar); the
  bar stays conservative rather than dilute the "under-the-radar" meaning.

## Explain (`stages/explain.py`)

`to_pick` builds the **flat** `Pick` (see `contract.md` → Pick): it sets the stable
`id = f"{hotel.source}:{hotel.id}"` (the search→refine identity, see `contract.md` → Refinement),
carries `score` and `rationale`,
maps the scorer's `subscores → why`, **surfaces** `name` / `area` / `price_per_night` / `currency` /
`rating` / `review_count` / `star_rating` / `description` / `amenities` / `url` / `image_url` up from
the hotel, sets `coordinates = hotel.location`, computes `distance_to_desired_km` (`haversine` to
`resolved.center` / the desired-area point via `utils/geo.py`, else `None`), and attaches the hotel's
`offers` (cheapest refundable + cheapest non-refundable, per `contract.md` → Budget and offers). The
`rationale` is **lens-aware**: the scorer's sentence plus a short clause for *why this projection*
(its price tier under `stratified_best`, a gem framing under `hidden_gems`), never contradicting the
scorer. The pipeline also sets `agent_status`, `warnings`, `resolved` (incl. `area`), and
`diagnostics` on the response.
