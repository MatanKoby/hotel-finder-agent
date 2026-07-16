# Request / response contract (`contracts.py`)

The stable typed surface this repo exposes **as a git submodule** to an orchestrator agent
("tripper"): `HotelSearchRequest` in, `HotelSearchResponse` out, via `search()`, with a `refine()`
companion for the feedback loop (see Refinement below). Built on the domain types in
`domain-model.md`. The agent is stateless (see `architecture.md`), so this contract is the entire
interface.

The response here is the **agent payload**. The orchestrator wraps it in its own **transport
envelope** (`{status: ok|error, error, hotel: <payload>}`) — that wrapper is orchestrator-owned and
not implemented in this repo. Our `agent_status` is the *data* outcome; the orchestrator's outer
`status` is the *transport* outcome (call/import/timeout). `empty` and `degraded` both map to
transport `status = ok`.

## The submodule API surface

- **Entry points (two):** `async def search(request: HotelSearchRequest, settings=None) ->
  HotelSearchResponse` for the initial query, and `async def refine(request: HotelRefineRequest,
  settings=None) -> HotelSearchResponse` for the feedback loop (see Refinement below). Each has a
  thin sync wrapper (`search_sync`, `refine_sync`) for non-async callers. All re-exported at the
  package top level (`from hotel_finder import search, search_sync, refine, refine_sync,
  HotelSearchRequest, HotelRefineRequest, HotelFeedback, HotelSearchResponse`).
- **Config is injected or read from env.** `settings=None` reads env / `.env`; the orchestrator may
  instead pass a `Settings`. **No `.env` is required when the library is imported** (see
  `config.md`).
- **The Pydantic v2 models are the contract, and the shared validator.** The orchestrator imports
  `HotelSearchRequest` from this submodule and constructs it *on its own side* before calling.
  Pydantic validates at construction and raises `pydantic.ValidationError` there,
  deterministically, before `search()` is ever entered. One validator, one source of truth, no
  drift between the two repos. `model_json_schema()` is available if the orchestrator is an LLM
  that wants the schema as a tool definition.

## Error philosophy: validate hard at the edge, never crash during work

- **Raise (only invalid input, pre-call):** malformed requests the shared validator rejects at
  construction (checkout not after checkin, `price_min > price_max`, out-of-range values). This
  is an orchestrator bug and surfaces on the orchestrator's side, before any work.
- **Warn, never drop, never crash (during work):** a provider being down, some hotels having no
  price, dates in the past, zero matches, the LLM scorer falling back to heuristic. These do not
  raise. They populate `HotelSearchResponse.warnings` and set `agent_status`, returning whatever
  results were obtained. The orchestrator sifts, retries, or asks the user.

## `HotelSearchRequest` (the request)

`extra="forbid"` (fail fast on an orchestrator typo, safe because the submodule is commit-pinned).

- `request_id: str` (auto uuid; the orchestrator may supply its own correlation id)
- `place: Place` (required, see below)
- `stay: Stay | None = None` (omit for content-only, no live prices)
- `guests: Occupancy = Occupancy()` — **trip-level** occupancy (see below)
- `guest_nationality: str = "US"` — **trip-level** traveler attribute; affects rates upstream
- `filters: Filters = Filters()`
- `lenses: list[LensName] | None = None` (None means all three)
- `picks_per_lens: int = 3` (ge=1)

### `intent` / `anchor_hotel` (the search mode) — a pair

- `intent: Intent = zone` — `zone` (default) is "find me somewhere in this area"; `anchor` is
  "find me peers of a named hotel".
- `anchor_hotel: str | None = None` — the hotel whose peers to find, used **only** when
  `intent = anchor`.

The default (`zone` / `None`) is the common path and leaves `anchor_hotel` inert, so the wire shape
is stable whether or not the orchestrator sets the pair. `intent = anchor` resolves `anchor_hotel`
and returns comparable hotels near it (the peer envelope + exclusion + fallback are described in
`pipeline.md` → Anchor intent). It **requires** a non-empty `anchor_hotel`: the shared validator
raises `ValidationError` at construction otherwise (an anchor request with no name is an
orchestrator bug, caught at the edge like the other validations above).

### `Place` (where to search) — accepts structured **and** free text

Both paths are accepted; structured fields win when present, `text` is the fallback the pipeline
geocodes (via Nominatim or LiteAPI place lookup, see `data-sources.md`). At least one usable path
is required.

- `country_code: str | None` (ISO-3166-1 alpha-2, e.g. `"ES"`) and `city: str | None` — the
  preferred path; maps straight onto LiteAPI discovery.
- `center: GeoPoint | None` + `radius_km: float | None = 5.0` — precise "near this point".
- `text: str | None` — free-text place name, geocoded internally when the structured fields are
  absent.
- `desired_area: str | None` — neighborhood bias for ranking, not a hard filter.

Validator: at least one of `city`, `center`, or `text` must be present.

### `Occupancy` (who is travelling) — trip-level

`Occupancy = {adults: int = 2 (ge=1), children_ages: list[int] = []}`. This is the orchestrator's
`Room` shape. It is **trip-level** (`request.guests`), shared context the flights and activities
agents want too, not nested under `stay`. Per-room control is the `stay.rooms` override below.

### `Stay` (dates + occupancy source, needed for real prices)

- `check_in: date`, `check_out: date`
- `currency: str = "EUR"`
- `rooms: list[Occupancy] | None = None` — **`None` derives a single room from `request.guests`.**
  When set, `rooms` **overrides** `guests` (multi-room bookings). `guests` is used *only* when
  `rooms` is `None`.

`guest_nationality` is **not** on `Stay` — it is trip-level (`request.guest_nationality`), because
it is a traveler attribute shared with the sibling agents. The pipeline threads it onto the rate
call.

### `Filters`

- `price_min / price_max: float | None` (ge=0)
- `min_star: int | None`, `min_guest_rating: float | None` (guest score, 0-10)
- `refundable: bool | None` — `None` (default) returns both a cheapest-refundable and a
  cheapest-non-refundable offer per hotel; `True`/`False` restricts to that kind.
- `must_have_amenities: set[Amenity]` (see `domain-model.md`)
- `property_types: set[str]` — empty (default) returns **all** lodging types (hotels, hostels,
  guesthouses, apartments, ...); a non-empty set narrows.

Validators enforce `price_min <= price_max` and `check_in < check_out`.

## `LensName`

`StrEnum`: `stratified_best`, `overall_standouts`, `hidden_gems`. The three projections of the
scored set (see `pipeline.md` → Lenses).

## `HotelSearchResponse` (the agent payload)

A **result envelope**, so partial results and problems are data the orchestrator reads, not
exceptions it must catch. The orchestrator wraps this in its transport envelope (top of this file).

- `request_id: str` — echoes the request
- `agent_status: Literal["ok", "empty", "degraded"]` — the **data** outcome: `ok` = results, no
  issue; `degraded` = results returned but something went wrong (see `warnings`); `empty` = valid
  query, nothing matched. (Renamed from `status`; the orchestrator owns the outer transport
  `status`.)
- `warnings: list[str]` — human-readable notes about anything that degraded a result
- `resolved: ResolvedQuery` — what was **actually** searched, for orchestrator reasoning
- `lenses: dict[LensName, list[Pick]]`
- `diagnostics: Diagnostics` (renamed from `meta`)

### `ResolvedQuery`

`city: str | None`, `area: str | None`, `center: GeoPoint | None`, `check_in / check_out: date |
None`, `currency: str | None`. Lets the orchestrator see which place/coords/dates the search ran
with (e.g. what `text` geocoded to) and decide whether to re-ask.

### `Pick` — flat, rendering-ready

One recommended hotel within a lens. **Flat** (no nested `hotel`): the fields the orchestrator needs
to render and reason are promoted to the top level, and internal-only fields (`raw`, full `sources`)
are not on the wire.

- `id: str` — **stable identity** for this hotel within a trip (`"{source}:{provider_id}"`, e.g.
  `"liteapi:lp1a2b3"`): globally unique, opaque to the orchestrator, and stable across the
  search→refine round-trip (the same hotel re-discovers with the same id, because both providers
  derive `Hotel.id` from a stable provider/fixture id). The orchestrator stores it and echoes it
  back (in `HotelFeedback.id` and `refine`'s `exclude`) to point at what the user liked or disliked.
  See Refinement below.
- `name: str`
- `score: float` (**0..1, normalized, comparable across lenses** — see below)
- `rationale: str` — human-readable "why this hotel"
- `why: dict[str, float]` — structured subscores; **free-form** (keys are scorer-dependent, so a
  fixed set would lie). Today: `value`, `location`, `character`, `gem_signal` (see `scoring.md`).
- `area: str | None`
- `distance_to_desired_km: float | None` — proximity to `desired_area` / `center`; **`None`** when
  neither was given
- `price_per_night: float | None`, `currency: str | None`
- `rating: float | None` (guest score, 0-10), `review_count: int | None`, `star_rating: int | None`
  (1-5)
- `description: str | None` — the "character" blurb
- `amenities: set[Amenity]`
- `coordinates: GeoPoint | None`
- `image_url: str | None` — provider-supplied photo (see `domain-model.md` → `Hotel.image_url`);
  **`None`** for providers/hotels without one (mock especially)
- `url: str | None`
- `offers: list[RateOffer]` — the priced results for this hotel (see Budget and offers below): up
  to two (cheapest refundable + cheapest non-refundable) when `filters.refundable` is unset, one
  when it is set. Empty when `stay` was omitted or no price was found.

**`score` is normalized to 0..1 and comparable across lenses.** It is the single overall score from
`scoring.md` (`clamp(0.5*value + 0.3*location + 0.2*character)`), already in `[0, 1]`. Every lens
surfaces that *same* overall score — the lenses differ in **selection** (which hotels), not in the
scale — so `stratified_best` must **not** re-normalize within a price tier, or cross-lens
comparability breaks.

### `RateOffer` (price info, read-only)

The orchestrator's `Offer` shape.

- `total: float`, `currency: str`, `per_night: float | None`
- `board: str | None` (e.g. `"Room Only"`, `"Breakfast Included"`)
- `refundable: bool` — whether this rate is refundable
- `over_budget: bool` — `True` when `total` exceeds `filters.price_max`; only appears in the
  budget-too-low fallback (below)

Read-only price information for M1. No booking token is carried: the LiteAPI prebook/book flow is
deferred (see `roadmap.md` and `data-sources.md` → LiteAPI). If booking is picked up later, an
opaque rate reference gets added here.

### Budget and offers (the price contract)

The hotel agent **is** the filter, not the orchestrator, so it does **not** return over-budget
hotels wholesale:

- **Normal case:** hotels within `filters.price_max` are returned across the lenses; every
  `RateOffer` has `over_budget = False`.
- Per hotel, offers are the **cheapest refundable** and **cheapest non-refundable** rate (or only
  the kind set by `filters.refundable`).
- **Budget-too-low fallback:** when too few (or no) hotels fit budget, rather than return empty the
  agent surfaces the cheapest available options (capped at `picks_per_lens`), each `RateOffer`
  flagged `over_budget = True`, sets `agent_status = "degraded"`, and adds a `warning` such as
  `"no hotels within EUR X; cheapest is EUR Y"`. The orchestrator sees the price floor, learns the
  budget is too low, and can relax it and re-query, without being spammed.

### `Diagnostics`

`providers_used`, `candidates_found`, `candidates_after_filter`, `shortlisted`, `scorer`,
`widened`, plus (on a `refine()` response) `refined: bool` and `round: int`. (Renamed from
`RecommendationMeta` / the `meta` field.)

Note: `scorer` reports the scorer that **actually ran**. If the LLM scorer falls back to heuristic
(no credentials, endpoint unreachable, bad output), `scorer` reads `heuristic` and a `warning`
records the fallback (see `scoring.md`, Batch M1e in `specflow/history/BUILD_QUEUE_DONE.md`).

## Refinement (`refine()` / `refine_sync()`): the feedback loop

The orchestrator's **second** call. After `search()` returns picks and the user marks some as
wanted or unwanted, the orchestrator calls `refine()` and gets a **new** `HotelSearchResponse`
that fits those signals, mapped by the exact same code (same return type as `search()`). This
mirrors the sibling activities agent's two-call design (search, then refine).

The agent stays **stateless** (`architecture.md`): `refine()` re-runs discovery from the original
trip context and applies the feedback, holding **no** memory between calls. Nothing is hoarded
across calls (it is a library inside a cloud function; a stored candidate set would leak until the
function is torn down). The identity round-trip works because `Pick.id` is stable (above): the
orchestrator echoes back the ids it was given, and `refine()` re-discovers the same hotels under
the same ids. The mechanics (exclusion, the wanted envelope, re-centring, the preference bias) are
in `pipeline.md` → Refine; the knobs are in `config.md` → Refine knobs.

### `HotelRefineRequest` (the refine request)

`extra="forbid"` (fail fast on an orchestrator typo, like `HotelSearchRequest`).

- `base: HotelSearchRequest` — the original trip context (place, stay, guests, filters, lenses,
  picks_per_lens, guest_nationality). Validated as its own model, so a malformed base raises
  `ValidationError` at construction, exactly as for `search()`.
- `wanted: list[HotelFeedback] = []` — hotels the user liked. Refine biases **toward** their shared
  attributes and surfaces **new** options like them (more that fit the bill, not the same list
  re-ranked), so the wanted hotels themselves are not returned again.
- `unwanted: list[HotelFeedback] = []` — hotels the user rejected. Excluded from the results, and
  their shared attributes are biased **against**.
- `exclude: list[str] = []` — `Pick.id`s already shown; not repeated (refine returns new options).
- `round: int = Field(default=1, ge=1)` — the refinement round, echoed into `diagnostics.round` for
  telemetry.

`wanted` and `unwanted` are independent: only `unwanted` is "not these"; only `wanted` is "more like
these"; all empty degrades to a plain re-search of `base`. Same invariants as `search()`: it never
raises on a data outcome (warnings + `agent_status`), imports keyless (mock provider + heuristic),
and is import-safe.

### `HotelFeedback` (a reduced, forgiving signal)

A trimmed echo of a prior `Pick`, deliberately easy for the caller to build (`extra="ignore"`, so a
caller that sends extra keys is not rejected).

- `id: str | None = None` — the `Pick.id` from a prior response, the **preferred identity**. `None`
  falls back to `name`.
- `name: str = ""` — the pick's name: the identity fallback when `id` is absent, and a useful signal
  for the LLM scorer.
- `attributes: HotelFeedbackAttributes | None = None` — optional echo of the pick's fields
  (`price_per_night`, `area`, `star_rating`, `amenities`, `property_type`), used for the attribute
  bias when the hotel is no longer in the freshly discovered set. `extra="ignore"`.
- `reason: str | None = None` — optional free text ("too far from the centre", "love the rooftop
  pool"), passed to the LLM scorer as context.

Identity resolves by `id` first (matched against the re-discovered candidates), then a
normalized-name match (the same matcher as `intent=anchor`, see `pipeline.md` → Anchor intent). A
feedback item that resolves to no current candidate still contributes its `attributes` to the bias
(see `pipeline.md` → Refine).

## Status vs the current code

**The reshape has fully landed (Batches C1 + C2).** `contracts.py` and the stages match the shape
described above: flat `Pick` (no nested `hotel`), trip-level `guests` + `guest_nationality`,
`agent_status`, `diagnostics` (`Diagnostics`), `Pick.why`, and a `0..1`-bounded `Pick.score`. C2
populated the last two fields: `Pick.image_url` (from the LiteAPI adapter's `main_photo`/`thumbnail`;
`None` for the mock and photo-less hotels) and `Pick.distance_to_desired_km` (haversine from the
hotel to the resolved search `center`; `None` when the center or the hotel's coordinates are
missing).

**Ahead of the code (refinement batch):** the Refinement surface above (`refine` / `refine_sync`,
`HotelRefineRequest`, `HotelFeedback`, `Pick.id`, `Diagnostics.refined` / `round`) is the design for
the in-flight feedback-loop batch (`BUILD_QUEUE.md`); it lands with that batch. Everything else
matches the code.
