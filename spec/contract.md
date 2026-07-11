# Request / response contract (`contracts.py`)

The stable typed surface this repo exposes **as a git submodule** to an orchestrator agent:
`HotelSearchRequest` in, `HotelSearchResponse` out, via one entry point. Built on the domain
types in `domain-model.md`. The agent is stateless (see `architecture.md`), so this contract is
the entire interface.

## The submodule API surface

- **Entry points:** `async def search(request: HotelSearchRequest, settings=None) ->
  HotelSearchResponse`, plus a thin sync wrapper `search_sync(request, settings=None)` for
  non-async callers. Both re-exported at the package top level
  (`from hotel_finder import search, search_sync, HotelSearchRequest, HotelSearchResponse`).
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
  raise. They populate `HotelSearchResponse.warnings` and set `status`, returning whatever
  results were obtained. The orchestrator sifts, retries, or asks the user.

## `HotelSearchRequest` (the request)

`extra="forbid"` (fail fast on an orchestrator typo, safe because the submodule is commit-pinned).

- `request_id: str` (auto uuid; the orchestrator may supply its own correlation id)
- `place: Place` (required, see below)
- `stay: Stay | None = None` (omit for content-only, no live prices)
- `intent: Intent = ZONE`
- `anchor_hotel: str | None = None` (for `anchor` intent, reserved; see `roadmap.md`)
- `filters: Filters = Filters()`
- `lenses: list[LensName] | None = None` (None means all three)
- `picks_per_lens: int = 3` (ge=1)

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

### `Stay` (dates + occupancy, needed for real prices)

- `check_in: date`, `check_out: date`
- `rooms: list[Occupancy] = [Occupancy()]`, where `Occupancy = {adults: int = 2,
  children_ages: list[int] = []}`
- `guest_nationality: str = "US"` (affects rates upstream), `currency: str = "EUR"`

### `Filters`

- `price_min / price_max: float | None` (ge=0)
- `min_star: int | None`, `min_guest_rating: float | None` (guest score, 0-10)
- `refundable: bool | None` — `None` (default) returns both a cheapest-refundable and a
  cheapest-non-refundable offer per hotel; `True`/`False` restricts to that kind.
- `must_have_amenities: set[Amenity]` (see `domain-model.md`)
- `property_types: set[str]` — empty (default) returns **all** lodging types (hotels, hostels,
  guesthouses, apartments, ...); a non-empty set narrows.

Validators enforce `price_min <= price_max` and `check_in < check_out`.

## `Intent`

`StrEnum`: `zone` (broad area search, fully handled) and `anchor` (peers of a named hotel,
**reserved**, not yet implemented; see `roadmap.md`).

## `LensName`

`StrEnum`: `stratified_best`, `overall_standouts`, `hidden_gems`. The three projections of the
scored set (see `pipeline.md` → Lenses).

## `HotelSearchResponse` (the response)

A **result envelope**, so partial results and problems are data the orchestrator reads, not
exceptions it must catch.

- `request_id: str` — echoes the request
- `status: Literal["ok", "empty", "degraded"]` — `ok` = results, no issue; `degraded` = results
  returned but something went wrong (see `warnings`); `empty` = valid query, nothing matched
- `warnings: list[str]` — human-readable notes about anything that degraded a result
- `resolved: ResolvedQuery` — what was **actually** searched, for orchestrator reasoning
- `lenses: dict[LensName, list[Pick]]`
- `meta: RecommendationMeta`

### `ResolvedQuery`

`center: GeoPoint | None`, `city: str | None`, `check_in / check_out: date | None`,
`currency: str | None`. Lets the orchestrator see which place/coords/dates the search ran with
(e.g. what `text` geocoded to) and decide whether to re-ask.

### `Pick`

- `hotel: Hotel` — carries location, description, amenities, coordinates (see `domain-model.md`)
- `score: float`, `subscores: dict[str, float]`, `rationale: str`
- `offers: list[RateOffer]` — the priced results for this hotel (see Budget and offers below): up
  to two (cheapest refundable + cheapest non-refundable) when `filters.refundable` is unset, one
  when it is set. Empty when `stay` was omitted or no price was found.

### `RateOffer` (price info, read-only)

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
  flagged `over_budget = True`, sets `status = "degraded"`, and adds a `warning` such as
  `"no hotels within EUR X; cheapest is EUR Y"`. The orchestrator sees the price floor, learns the
  budget is too low, and can relax it and re-query, without being spammed.

### `RecommendationMeta`

`providers_used`, `candidates_found`, `candidates_after_filter`, `shortlisted`, `scorer`,
`widened`.

Note: `scorer` reports the scorer that **actually ran**. If the LLM scorer falls back to heuristic
(no credentials, endpoint unreachable, bad output), `scorer` reads `heuristic` and a `warning`
records the fallback (see `scoring.md`, Batch M1e in `BUILD_QUEUE.md`).

## Status vs the current code

`contracts.py` still carries the **v1 names** (`HotelQuery`, `Recommendations`, flat `location` /
`guests`). The design above (rename to `HotelSearchRequest` / `HotelSearchResponse`, `Place` /
`Stay` / `Filters`, the envelope, `RateOffer`) is the M1 target; the code refactor to match is a
batch in `BUILD_QUEUE.md`.
