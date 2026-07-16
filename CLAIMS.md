# Claims

Execution-state ledger, managed by coding agents. Records who is working on what and the recent
completion log. The user does not normally edit this. Procedures:
`specflow/procedures/claim-batch.md` and `specflow/procedures/finish-batch.md`.

Entry format:

```
### Batch N — <short title>
- Owner: <agent>
- Started: YYYY-MM-DD HH:MM        (UTC)
- Finished: YYYY-MM-DD HH:MM       (only in Completed)
- Commit: <short SHA>              (only in Completed)
- Handoff note: ...                (only when a mid-batch handoff occurred)
```

## In progress

<!-- One entry per actively claimed batch. -->

## Completed

### Batch P7 — Refinement entry point (feedback loop)
- Owner: claude
- Started: 2026-07-16 15:43
- Finished: 2026-07-16 18:54
- Commit: 8775700

**What shipped.** A second stable entry point `refine()` / `refine_sync()` parallel to `search`,
returning the same `HotelSearchResponse`, so the orchestrator runs a two-call loop: `search`, then
`refine` with the user's wanted / unwanted marks on the prior response. The agent stays **stateless**
(a cloud-function-friendly library that hoards no candidate set between calls): `refine()`
re-discovers from `request.base` each call and applies the feedback.

**Contract (`contracts.py`).** New `Pick.id` = `"{source}:{id}"` (globally unique, opaque, **stable
across the search→refine round-trip** because both providers derive `Hotel.id` from a stable
provider/fixture id; set in `stages/explain.py`). New `HotelRefineRequest` (`base` /`wanted` /
`unwanted` / `exclude` / `round`, `extra="forbid"`), `HotelFeedback` + `HotelFeedbackAttributes` (a
reduced, forgiving `extra="ignore"` echo of a prior pick: `id`, `name`, `attributes`, `reason`), and
`Diagnostics.refined` + `round`. Exports `refine`, `refine_sync`, `HotelRefineRequest`,
`HotelFeedback`, `HotelFeedbackAttributes`.

**Stage (`stages/refine.py`).** `match_feedback` (by `Pick.id` first, then the `find_anchor`
normalized-name matcher); `plan_refine` builds the **exclusion set** (`wanted ∪ unwanted ∪ exclude`,
so refine returns **new** options, never the rejected/liked ones again), the **wanted envelope**
(`RefineEnvelope`, a multi-hotel analogue of the anchor envelope: price window across the wanted
prices, star/rating floors near the group minimum, re-centre on the wanted centroid; `to_criteria`
only ever tightens); and `apply_preference` (a bounded post-scoring nudge `refine_bias_weight *
(sim_wanted − sim_unwanted)` over area / price band / star tier / amenities, surfaced as
`why["preference"]`, applied to whatever scorer ran so the bias is deterministic offline).

**Pipeline (`pipeline.py`).** `refine()` async + `refine_sync()`; the shared tail of `search()` was
extracted into `_assemble` (and discovery into `_discover`) so both entry points build the response
through one path. `SearchContext` gained `preference`, threaded into the LLM prompt (`scoring/llm.py`:
wanted/unwanted profiles + `reason` text, so live rationales stay coherent; the deterministic nudge
covers the heuristic path). `config.py`: 6 `refine_*` knobs (`refine_radius_km=3.0`,
`refine_price_low_factor=0.7`, `refine_price_high_factor=1.4`, `refine_star_tolerance=1`,
`refine_rating_tolerance=1.0`, `refine_bias_weight=0.15`).

**Spec:** `contract.md` (Refinement section + `Pick.id`), `pipeline.md` (Refine section),
`config.md` (Refine knobs), `scoring.md` (Preference bias), `dev-guide.md`, `roadmap.md` — commits
`e7d269b`, `d896524`.

**Verification.** `make check` green (ruff + mypy strict; **pytest 136 passed, +17** in
`tests/test_refine.py`: units for matching / envelope / preference / exclusion, and e2e over the mock
provider for unwanted-excluded, wanted-favored-and-not-repeated, id round-trip, exclude list, and
empty-feedback-equals-search). Ran the orchestrator's keyless "Done" command end to end from a
`.env`-free dir: `refine_sync(...)` → `agent_status=ok`, `refined=True`, `scorer=heuristic`, unwanted
excluded, wanted not repeated, stable `mock:bcn-*` ids, positive preference nudges on wanted-like
picks. **Live LLM path unverified** (Nebius creds unset); validate with `make eval` when configured.

### Batch P3 — ANCHOR intent (peers of a named hotel)
- Owner: claude
- Started: 2026-07-14 06:21
- Finished: 2026-07-14 06:55
- Commit: e69c049

**What shipped.** The reserved `anchor` intent is now implemented: `intent=anchor` +
`anchor_hotel` finds **peers of a named hotel** instead of a broad area. New **`stages/anchor.py`**:
`find_anchor(candidates, name)` locates the anchor among the discovered candidates by
`normalize_text` name (exact match, else a **unique** containment match either direction; ambiguous
or absent → `None`); `anchor_envelope(anchor, settings)` derives an `AnchorEnvelope` — **proximity**
(anchor coords + `anchor_radius_km`), a **price window** (`anchor_price_low_factor` ..
`anchor_price_high_factor` × the anchor's price), and **class floors** (`min_star =
star - anchor_star_tolerance`, `min_guest_rating = rating - anchor_rating_tolerance`); each dimension
is dropped when the anchor lacks that attribute, and `is_empty()` reports "no usable constraint".
`AnchorEnvelope.to_criteria(base)` folds the envelope into the request's own `Filters` so it only
ever **tightens** (stricter price/star/rating bound wins; must-have amenities pass through) and the
anchor's location replaces the request centre for peer proximity.

**Pipeline (`pipeline.py`).** `_filter_with_widening` was refactored to take the `FilterCriteria`
**base** directly (was `(request, center)`), so `search()` builds the base once and the anchor
branch can swap it. New `_apply_anchor` runs between price-band derivation and the hard filter (only
when `intent is Intent.ANCHOR`): locate the anchor, **exclude it** from candidates (it is the
reference, not a recommendation), tighten `base` to the envelope, and re-centre ranking on the anchor
(`resolved.center = anchor.location`, so the shortlist proximity bias **and**
`distance_to_desired_km` measure from the anchor). Anchor not found, or too thin to constrain peers →
`warning` + `agent_status=degraded` + a broad **zone** fallback over the same candidates (never
crashes, per `contract.md` → Error philosophy). **Contract (`contracts.py`):** a `model_validator`
raises at construction when `intent=anchor` has no non-empty `anchor_hotel` (the sole anchor
validation, caught at the edge). **Config:** 5 `anchor_*` knobs (`anchor_radius_km=3.0`,
`anchor_price_low_factor=0.6`, `anchor_price_high_factor=1.6`, `anchor_star_tolerance=1`,
`anchor_rating_tolerance=1.0`). Spec: `contract.md` (intent/anchor_hotel pair + validator),
`pipeline.md` (Anchor intent section), `config.md` (knob table), `roadmap.md` (ANCHOR marked done) —
commit `a125f75`.

**Verification.** `make check` green (ruff + mypy strict; **pytest 119 passed, +14**). New
`tests/test_anchor.py` (11): `find_anchor` exact/containment/ambiguous/no-match/empty;
`anchor_envelope` full/partial/empty; `to_criteria` tightens-never-loosens; and end-to-end over the
mock — anchor "Diagonal Upscale Suites" returns exactly its 2 in-envelope peers (Barceloneta Beach
Inn, El Born Riverside), excludes itself, sets `resolved.center` to the anchor, and every pick sits
inside the price window / radius / class floors; a partial name still resolves; a request `price_max`
below the window still caps peers; an unknown anchor degrades to a broad zone search with a "not
found" warning. Plus 3 contract tests (validator raises; builds with a name; zone default inert).
**Drove the flow manually** (offline mock, heuristic): the anchor path returns the 2 peers ranked
around the anchor with distances 2.06/2.88 km; the not-found path degrades with the expected warning
and the whole city is searched.

**Deferred / notes.** Peer discovery is scoped to the request's `place` (the anchor's city/area),
matching the anchor **within** the discovered set — there is no global by-name hotel lookup (LiteAPI
discovery has no name-search; a request always carries a `place`, so this is sufficient). Rationales
are **not** anchor-aware yet (picks are peers by construction, and the orchestrator knows it asked
for anchor peers; adding "a peer of X" phrasing would thread the anchor name into `stages/explain.py`
— a cosmetic follow-up). The `anchor_*` factors are untuned starting values (same stance as the other
thresholds, `roadmap.md`). Not verified against a live source, but the intent branch is
provider-agnostic (operates on the deduped candidate set). Remaining open work: **P4** (more
sources), **P5** (web-search backup) — each open-scope, `spec-edit` first; plus the two M1 flags
(`filters.property_types` unenforced, `over_budget` per-night vs total) and eval finding 6 (semantic
metrics). `dev` pushed to `origin/dev`.

### Batch P2 — Result-quality improvements
- Owner: claude
- Started: 2026-07-13 17:39
- Finished: 2026-07-14 05:06
- Commit: fb83c93

**What shipped.** The P1/P6 live-eval findings (`spec/roadmap.md` → Baseline findings), items 1-5.
(1) **Star-tier lens fallback** — `stratified_best` (`stages/lenses.py`) stratifies by **star tier**
(highest first, capped to `len(PriceBand)` so the pick cap holds; top-overall if stars are also
absent) when **no** candidate has a price band, so a content-only search (no rates → no bands) still
fills the lens. (2) **Desired-area ranking point** — `_resolve` (`pipeline.py`) now distinguishes a
**filter centre** (explicit `place.center` / geocoded free text; bounds the hard radius + provider
discovery) from a **desired point** (the filter centre, else a geocoded `desired_area`); the desired
point is a **soft ranking bias, never a hard radius**, becomes `resolved.center`, and drives
proximity ranking + `distance_to_desired_km` for area-string searches. New
`Settings.geocode_desired_area` (default on; **off in `eval_settings()`** so `make check` stays
network-free, exercising the area-string fallback offline). (3) **Graded heuristic location**
(`scoring/heuristic.py`) — name-only fit is exact(1.0)/partial-word(0.55-0.9)/different(0.35, below
the 0.6 no-signal neutral), not a flat 1.0/0.5. (4) **Grounded LLM location** (`scoring/llm.py`) —
`_hotel_payload` feeds `coordinates` + `distance_to_desired_km` + `in_desired_area` and the prompt
scores `location` from them instead of guessing. (5) **Honest gem rationale** — the "few reviews"
phrasing is gated on a known-low `review_count`; the LLM is told not to gem-label well-reviewed
hotels; rationales are **lens-aware** (price tier under `stratified_best`, gem framing under
`hidden_gems`) in `stages/explain.py`. **Gentle widening** (`pipeline.py`) — middle steps widen the
price band by `widen_price_factor` (0.5), only the final step drops the bounds (preserves the
budget-too-low fallback); `max_widen_steps` 2→3, `WIDEN_PRICE_FACTOR` added. Spec: `scoring.md`,
`config.md`, `pipeline.md`, `roadmap.md` (commit `85eb32b`).

**Verification.** `make check` green (ruff + mypy strict; **pytest 105 passed, +15**). Re-measured
with `make eval`: offline-hermetic table matches the prior baseline (no regression); with
`geocode_desired_area` on the zone/content scenarios now report `dst%=100%`. **Verified live**
against real LiteAPI Barcelona + Nebius Token Factory (`Qwen/Qwen3-32B`, thinking off):
content-only now fills `stratified_best` via star tiers (5/4/3-star spread), and the LLM `location`
subscore tracks distance (0.9@0.2km, 0.8@0.8km, 0.8@1.0km) instead of a flat `1.00` for every hotel.

**Deferred / notes.** Finding 6 (semantic/quality eval, not just structure) stays open. The
heuristic weightings and price-band cutoffs remain **untuned** on purpose — safe tuning wants the
finding-6 ground truth, not blind number changes. `hidden_gems` is often empty on real data
(popular-city hotels are well-reviewed → few clear the "under-the-radar" bar); the bar stays
conservative by design. The LLM-latency/timeout issue is operational (tracked in `roadmap.md`), not
part of P2. `.env` here pins a non-existent `Qwen/Qwen2.5-32B-Instruct`; live LLM runs need
`LLM_MODEL=Qwen/Qwen3-32B` + `LLM_DISABLE_THINKING=true` (per P6). Next open work: **P3** (anchor
intent), **P4** (more sources), **P5** (web-search backup) — each open-scope, needs a `spec-edit`
first; plus the two long-standing M1 flags (`filters.property_types` unenforced, `over_budget`
per-night vs total). `dev` pushed to `origin/dev`.

### Batch P6 — Live-eval wiring + LLM thinking-off toggle
- Owner: claude
- Started: 2026-07-13 14:09
- Finished: 2026-07-13 14:26
- Commit: f22fdf9

**What shipped.** Made `make eval` usable for real local evaluation and reached the closest-to-
orchestrator LLM on Nebius Token Factory. (1) `tests/eval/report.py` now reads `Settings()` from the
environment / `.env` (was pinned offline), so the same catalog runs live (real LiteAPI + LLM); the
tests stay hermetic-offline. The report gained a config banner and a per-scenario **scorer** column
(`metrics.ScenarioMetrics.scorer` = `diagnostics.scorer`) so an LLM→heuristic fallback is visible.
(2) Added `Settings.llm_disable_thinking` (`LLM_DISABLE_THINKING`), wired into the OpenAI-compatible
backend as `extra_body={"chat_template_kwargs": {"enable_thinking": false}}`; no-op on models without
a thinking mode. `.env.example` switched to `Qwen/Qwen3-32B` + `LLM_DISABLE_THINKING=true`.
Motivation: Token Factory has no `qwen2.5-32b`; `Qwen3-32B` is the closest (dense 32B) but its
default thinking pass times out on the scorer prompt (disabling it is fast **and** matches the
orchestrator's non-thinking `qwen2.5-32b`). Spec: `config.md`, `scoring.md`, `dev-guide.md` (commit
`62ce197`). `make check` green, **92 tests (+2** OpenAI-backend `extra_body` tests**)**. Verified
live: all 8 eval scenarios scored by `scorer=llm`, 0 fallbacks, all contract invariants pass against
real LiteAPI Barcelona hotels + Nebius Token Factory. Deferred: a cosmetic "Event loop is closed"
teardown trace from the LiteAPI httpx client under per-call `asyncio.run` (does not affect results);
the serverless-endpoint backend (Ollama REST) has no thinking-off knob yet (uses `enable_thinking`
differently).

### Batch P1 — Evaluation harness and test scenarios
- Owner: claude
- Started: 2026-07-12 19:29
- Finished: 2026-07-12 20:03
- Commit: a77c522

**What shipped.** A result-quality evaluation harness under `tests/eval/`, driving representative
`search()` requests end to end on the offline mock provider + heuristic scorer (deterministic, no
network, $0). Three modules: `scenarios.py` (the 8-scenario catalog — `HotelSearchRequest` + a
declarative `Expect` — the single source of truth shared by tests and report, provider-agnostic so
`eval_settings()` can be repointed at liteapi+llm), `metrics.py` (`check_invariants()` = the
contract guarantees that must hold for any request/provider: score range, within-lens dedupe, one
score per hotel across lenses, status/warning coherence, offer currency + over-budget/refundable
sanity, `resolved` echo, centre→distance; plus `evaluate()` for countable signals), and
`report.py` (`make eval` — prints the baseline metrics table, exits non-zero on any invariant
violation). Scenarios cover the batch's list: budget-ok, over-budget fallback, refundable
true/false, content-only, thin-result widening, geo-centre. Added `make eval` to the Makefile and
documented the harness in `spec/dev-guide.md` (commit `5717d70`). `make check` green: **90 tests
(+17)**, ruff + mypy clean. Baseline surfaced two real content gaps the mock exposes (0% image_url,
0 non-refundable offers) — expected, LiteAPI fills both. This is the baseline Batch P2 tunes
against. No follow-ups deferred.

### Batch C2 — Provider-backed enrichment (image_url, distance_to_desired_km)
- Owner: claude
- Started: 2026-07-12 13:52
- Finished: 2026-07-12 14:10
- Commit: 38ae7d4

**What shipped.** Populated the two `Pick` fields C1 declared nullable, completing the contract
reshape. **`image_url`:** added `Hotel.image_url` (`models.py`, per `spec/domain-model.md`); the
LiteAPI adapter maps `main_photo` (preferred) / `thumbnail` (fallback), keeping both in `raw`
(`spec/data-sources.md` mapping-table row updated to route them to `image_url`); the mock leaves it
`None`; `explain.py` surfaces `hotel.image_url` on the flat `Pick`. **`distance_to_desired_km`:**
`explain.to_pick`/`to_picks` now take the resolved search `center` and compute
`haversine(hotel.location, center)` via `utils/geo.py`, rounded to 2 dp, `None` when the center or
the hotel's coordinates are missing; the pipeline threads `resolved.center` through `_build_lenses`.
`review_count` + `description` already flowed from the adapter (C1 surfaced them) — now covered
end-to-end so they aren't silently `None`. Also fixed the stale README example (pre-C1
`pick.hotel.name` / `response.status`) in a preceding `docs:` commit, and updated
`spec/contract.md`'s "Status vs the current code" note (reshape fully landed, no divergence).

**Verification.** `make check` green (ruff + mypy strict on 31 source files); pytest 73 passed
(+7: `tests/test_explain.py` `to_pick` distance computed / `None` without center / `None` without
coords / `image_url` passthrough; `tests/test_liteapi.py` adapter `image_url` main_photo→thumbnail
fallback + absent, and an end-to-end stub asserting `image_url`/`review_count`/`description` reach
the picks and city-only distance stays `None`; `tests/test_pipeline.py` distance populated when a
center resolves). **Verified live** over the LiteAPI sandbox: real Barcelona hotels returned real
`main_photo` URLs and `distance_to_desired_km` 0.4-1.4 km from a Sagrada Família center, with
`review_count` + `description` populated.

**Deferred / notes.** `distance_to_desired_km` is measured to `resolved.center`, not to a geocoded
`place.desired_area` point (`desired_area` is a string bias, never geocoded to a point in this repo);
if a true desired-area distance is wanted later, geocode `desired_area` and pass that point instead.
The contract reshape (C1 + C2) is complete. Next open work: **P1** (eval harness) then **P2**
(quality); the two M1 correctness flags (`filters.property_types` unenforced, `over_budget` per-night
vs total) remain open and each needs a `spec-edit` first. `dev` is pushed to `origin/dev`.

### Batch C1 — Contract reshape (flatten Pick, renames, trip-level guests)

### Batch C1 — Contract reshape (flatten Pick, renames, trip-level guests)
- Owner: claude
- Started: 2026-07-12 05:57
- Finished: 2026-07-12 11:03
- Commit: 9723b95

**What shipped.** Refactored `contracts.py` and the response/request-building stages to the
orchestrator-agreed flat/renamed wire shape (`spec/contract.md`), with **no new provider data** (the
two new `Pick` fields return `None` until C2). **Request:** trip-level `guests: Occupancy`
(default `Occupancy()`) and `guest_nationality: str = "US"`; `Stay.rooms` is now
`list[Occupancy] | None = None` (`None` derives one room from `guests`, a set value **overrides**);
`guest_nationality` removed from `Stay`; `intent`/`anchor_hotel` keep inert defaults, off the
documented wire. **Response:** `status` → `agent_status`; `meta` → `diagnostics`
(`RecommendationMeta` → `Diagnostics`); `ResolvedQuery` gained `area` (echoes `place.desired_area`).
**Pick (flattened):** `name`/`area`/`price_per_night`/`currency`/`rating`/`review_count`/
`star_rating`/`description`/`amenities`/`coordinates`/`url` promoted up from `Hotel`; no nested
`hotel` (nor `raw`/`sources`) on the wire; `subscores` → `why`; `score` bounded `Field(ge=0, le=1)`;
`image_url` / `distance_to_desired_km` declared but `None`. **Pipeline/provider:** derive `[guests]`
when `stay.rooms is None`; thread trip-level `guest_nationality` onto the rate call
(`api.hotels_rates` now takes `rooms` + `guest_nationality`, no longer read off `Stay`).
`explain.py` builds the flat `Pick` and maps `subscores → why`. Top-level exports swapped
`RecommendationMeta` → `Diagnostics`. Updated `spec/contract.md`'s "Status vs the current code" note
to record the reshape landed (only C2 fields remain).

**Verification.** `make check` green (ruff + mypy strict on 31 source files); pytest 66 passed
(+1: `test_pipeline.py::test_pick_score_normalized_and_stable_across_lenses` asserts `Pick.score ∈
[0,1]` and that a hotel appearing in multiple lenses carries the **same** overall score, i.e. no
per-tier re-normalization in `stratified_best`; the rest updated for the renames/flatten). Ran the
edited `examples/orchestrator_sim.py` offline (mock): renders the flat picks (`pick.name`, `area`,
`agent_status`, `diagnostics`) with real offers across all three lenses.

**Deferred / notes.** `Pick.image_url` and `Pick.distance_to_desired_km` are declared and return
`None` — **Batch C2** populates them (provider `main_photo`/`thumbnail` + `haversine` to
`resolved.center`). Next: C2, then P1 (eval harness targets this final contract). `dev` is pushed to
`origin/dev`.

### Batch M1e — Integration surface + minimal orchestrator example
- Owner: claude
- Started: 2026-07-11 15:02
- Finished: 2026-07-11 15:44
- Commit: b1d06d4

**What shipped — Milestone 1 is submodule-ready.** `examples/orchestrator_sim.py` stands in for the
orchestrator: it builds a `HotelSearchRequest` from the exported models, calls `search()` (shows
`search_sync()`), and pretty-prints the `HotelSearchResponse` (status, warnings, resolved query,
lenses, priced offers). Finalized the top-level import surface (`search`/`search_sync` + request/
response + all sub-models + `Settings`; `py.typed` already shipped), removed the obsolete
`demo.py` and its console-script entry, and pointed `make run` at the example. Fixed env-based
provider selection: `ENABLED_PROVIDERS` now accepts a plain comma-separated string (via `NoDecode`
+ a validator), not only JSON — `ENABLED_PROVIDERS=mock` / `mock,liteapi` now work. Rewrote
`README.md` around submodule usage (add-submodule + `pip install -e` + `await search(...)`, the
validator/envelope contract, data/scoring config, layout).

**Verification.** `make check` green (ruff + mypy strict on 31 source files); pytest 65 passed
(+5 in `tests/test_integration.py`: exports present, no keys/`.env` required to import + run mock,
offline mock search, the example's `run()` offline, and `ENABLED_PROVIDERS` env parsing). A fresh
`python -m venv` + `pip install -e .` exposes `from hotel_finder import search, HotelSearchRequest`.
`make run` prints the envelope offline (mock + heuristic) **and** live end-to-end over LiteAPI
(50 real Barcelona hotels → filtered → shortlisted → scored → three lenses with real
refundable/non-refundable offers).

**Milestone 1 complete (M1a–M1e).** The submodule: import → build `HotelSearchRequest` → `search()`
→ `HotelSearchResponse` with real LiteAPI hotels/prices across three lenses, Nebius LLM scoring with
heuristic fallback (both offline-verified), free-text geocoding, no mandatory `.env`, no crashes.
Deferred to post-M1: live LLM verification (needs a key/endpoint), `filters.property_types`
enforcement, evaluation harness (P1), quality tuning (P2), ANCHOR intent (P3), more sources (P4),
web-search backup (P5). `dev` branch is local-only and **unpushed** — run `git push -u origin dev`.

### Batch M1d — Nebius LLM scoring (two transports) + effective-scorer reporting
- Owner: claude
- Started: 2026-07-11 14:54
- Finished: 2026-07-11 15:02
- Commit: c843b6d

**What shipped.** `LLMScorer` now has two transports behind a small `_ChatBackend` seam:
**Backend A** (OpenAI-compatible, the `openai` SDK against `llm_base_url` + `llm_api_key` +
`llm_model` — Nebius Token Factory / Groq / etc.) and **Backend B** (`scoring/nebius_endpoint.py`, a
thin Ollama-REST client: `GET /api/tags` liveness + single-model auto-discovery, `POST /api/chat`,
bearer `nebius_endpoint_token`, no API key, brief cold-start retry). The backend is chosen by
`llm_backend`/env (`auto` → endpoint if `NEBIUS_ENDPOINT_URL` set, else openai if `LLM_API_KEY`
set, else none). Both share the prompt, the `{"scores":[...]}` parse, and the one repair retry, and
both fall back to the heuristic on any failure. Added `scoring/base.py:ScoreReport` (effective
`scorer` + `warnings`) and `HotelScorer.report`; the heuristic reports `heuristic`, the LLM scorer
reports `llm` on success or `heuristic` + a warning on fallback. The pipeline now sets
`meta.scorer` from the scorer that **actually ran** and surfaces the fallback warning. Config gained
`llm_backend` + `nebius_endpoint_url`/`_token`/`_model`.

**Verification.** `make check` green (ruff + mypy strict on 32 source files); pytest 60 passed
(+7: `test_llm_scorer.py` valid/invalid/omitted/no-backend/repair-retry with an injected backend;
`test_nebius_endpoint.py` `/api/tags` auto-discovery + `/api/chat` via `httpx.MockTransport`,
no-models error, backend selection auto/forced, and a scorer run over the endpoint backend; plus a
pipeline test that `scorer=llm` with no creds reports `meta.scorer=heuristic` + a warning).

**Deferred / notes.** No **live** LLM verification: neither a Token Factory key nor a Nebius
endpoint is configured in `.env` (the offline stubbed paths cover both transports). Scoring
weightings are unchanged (P2). Next and last for M1: **M1e** (integration surface, no-mandatory-
`.env`, `py.typed`, `examples/orchestrator_sim.py`, remove `demo.py`, README). `dev` remains
local-only, unpushed.

### Batch M1c — Place resolution (structured passthrough + text geocoding)
- Owner: claude
- Started: 2026-07-11 14:43
- Finished: 2026-07-11 14:54
- Commit: 8aa7f36

**What shipped.** `utils/geocode.py`: a `Geocoder` protocol with a free, keyless
`NominatimGeocoder` backend (OpenStreetMap, sends the required `User-Agent`), a `GeoResult`
(`lat`/`lon`/`city`/`country_code`), and `make_geocoder(settings)`. The pipeline's resolve step is
now async: a `Place` that gives only `text` is geocoded into `center` + `city` + `country_code`;
`_resolve` returns the `ResolvedQuery` **and an effective request** whose `place` carries the
resolved fields, so the LiteAPI provider discovers against them. Structured places pass straight
through and never build a geocoder. A geocode failure or no-match adds a `warning` and proceeds
(never crashes). Config gained `nominatim_base_url` / `geocoder_user_agent` / `geocoder_timeout`.

**Verification.** `make check` green (ruff + mypy strict on 31 source files); pytest 53 passed
(+6 in `tests/test_geocode.py`: Nominatim JSON parsing via `httpx.MockTransport`, empty-result →
None, pipeline geocode-success/failure/no-match, and structured-place-skips-geocoding). Verified
**live** against Nominatim (Sagrada Familia → Barcelona/ES; Shibuya → Tokyo/JP).

**Deferred / notes.** Backend is Nominatim only; `spec/data-sources.md` mentions trying LiteAPI's
place lookup first — left as a future swap behind the `Geocoder` interface (Nominatim is free and
needs no key, so it works without a LiteAPI key). Next: M1d (Nebius scoring, two transports) then
M1e (integration surface + example). `dev` remains local-only, unpushed.

<!-- Recent finishes, newest first. Older entries archived to specflow/history/CLAIMS_DONE.md. -->

### Batch M1b — LiteAPI provider (real hotels, content, and prices)
- Owner: claude
- Started: 2026-07-11 14:31
- Finished: 2026-07-11 14:43
- Commit: 00247df

**What shipped.** A self-contained `providers/liteapi/` folder: `api.py` (async `httpx`
`LiteApiClient` for `GET data/hotels` discovery+content and `POST hotels/rates`, `X-API-Key`
header), `adapter.py` (maps a `data/hotels` item → `Hotel` per the `spec/data-sources.md` mapping
table: coords, `city`→area, `stars`→`star_rating`, guest `rating` kept 0-10, `reviewCount`,
`facilityIds`→`Amenity` via the shipped `facilities.json` id→name dict + `normalize_amenity`,
HTML `hotelDescription` stripped; and `hotels/rates` → the **cheapest refundable + cheapest
non-refundable** offer per hotel, `refundableTag` "RFN"→True/"NRFN"→False), and `provider.py`
(the two-call join; rates fetched only when `stay` is present). The registry moved to **provider
factories** (`Settings -> HotelProvider`) so real sources get credentials; the pipeline now calls
`get_providers(names, settings)`. `pipeline._offers_for` prefers provider-normalized offer dicts in
`hotel.raw["offers"]` (falls back to synthesizing from `price_per_night` for the mock), applying the
budget flag and `refundable` filter once. Added `LITEAPI_API_KEY`/`LITEAPI_BASE_URL`/
`LITEAPI_TIMEOUT` to `Settings`, `httpx` to deps, and `utils.strip_html`. LiteAPI is **disabled by
default** (`enabled_providers=["mock"]`), so CI stays offline.

**Verification.** `make check` green (ruff + mypy strict on 30 source files); pytest 47 passed
(+7 in `tests/test_liteapi.py`: adapter mapping from the recorded fixtures, cheapest-of-each-kind
offers, content-only, stubbed-client provider join, and a stubbed end-to-end pipeline run incl.
over-budget fallback and the refundable filter). Also **verified live** against the LiteAPI sandbox
key in `.env`: `search()` with `enabled_providers=["liteapi"]` returned 50 real Barcelona hotels
with real names, stars, 0-10 ratings, and EUR rates + refundable flags, `status=ok`.

**Deferred / notes.** `filters.property_types` narrowing is **not enforced** yet: LiteAPI gives an
integer `hotelTypeId` (stored in `raw`) but there is no recorded type-id→label dictionary to match
against (parallel to `facilities.json`); flag for the user — either record that dict or drop the
field. Rates use the retail `total`; `suggestedSellingPrice`/`rateId`/`offerId` are ignored (booking
deferred). No `.env` needed for the offline path; live use needs `LITEAPI_API_KEY`. Next: M1c
(place resolution / geocoding) and M1d (Nebius scoring), then M1e. `dev` remains local-only,
unpushed.

### Batch M1a — Contract + the submodule search API
- Owner: claude
- Started: 2026-07-11 11:15
- Finished: 2026-07-11 14:31
- Commit: 518dd45

**What shipped.** Refactored `contracts.py` from the v1 `HotelQuery`/`Recommendations` to the
submodule surface in `spec/contract.md`: `HotelSearchRequest` (`Place`/`Occupancy`/`Stay`/`Filters`,
`extra="forbid"`, price/date validators) in, a `HotelSearchResponse` envelope
(`status` ok/empty/degraded + `warnings` + `resolved` + `lenses` + `meta`) out, plus `RateOffer`,
`ResolvedQuery`, and `Pick` gaining `offers`. `pipeline.py` now exposes `async search()` and a thin
`search_sync()`, resolves `Place` into `ResolvedQuery` (free-text geocoding stubbed → M1c), turns
provider failures into warnings (never fatal), derives read-only offers from `price_per_night` when
a `stay` is present (real LiteAPI rates → M1b), and implements the budget-too-low fallback
(over-budget offers flagged, `status=degraded`, price-floor warning). Introduced an internal
`context.py:SearchContext` so shortlist/scorers no longer depend on the public request shape.
Folded in the already-specced **guest-rating rescale to 0-10** (`models.py` bound, heuristic
`value` `rating/10` + gem `(rating-8)/2`, shortlist, and the mock Barcelona fixtures ×2), since the
LiteAPI adapter (M1b) targets a 0-10 `Hotel.rating`. Wired `min_star`/`min_guest_rating` into
`stages/filtering.py`. Top-level re-exports `search`/`search_sync` + request/response + sub-models +
`Settings`; `demo.py` updated to the new API (deleted in M1e).

**Verification.** `make check` green (ruff + mypy strict on 26 source files); pytest 40 passed
(was 26) including new `tests/test_contract.py` (validation raises at construction) and envelope /
offers / status / `search_sync` coverage in `tests/test_pipeline.py`. `from hotel_finder import
search` and `python -m hotel_finder.demo` both run offline with the heuristic scorer.

**Deferred / notes.** No mandatory `.env`, `py.typed`, and the `examples/orchestrator_sim.py` proof
are M1e. Real prices/refundability come from M1b (M1a synthesizes one refundable offer per hotel
from the provider price). `over_budget` is computed per-night (consistent with the existing
price filter); `spec/contract.md` phrases it as "total exceeds price_max" — flag for the user if a
total-vs-total budget is wanted. `dev` branch is local-only and unpushed (HTTPS remote, no
non-interactive auth).
