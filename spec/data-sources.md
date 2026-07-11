# External data sources (evaluated hotel / accommodation APIs)

This is the catalog of real-world data providers evaluated for supplying live lodging data: what
each offers, its free terms, and which is chosen for Milestone 1. The **internal architecture**
for plugging a source in (one folder per source, `api.py` + `adapter.py`) is in `providers.md`;
this file is the external market catalog and the sourcing decisions. Milestone status lives in
`roadmap.md`.

**The M1 bar (see `roadmap.md`):** at least one free source returning real results, ideally a
**single** source covering location + description + price so the "best value per tier" lens has
prices to group on.

## Chosen for Milestone 1: LiteAPI (Nuitée)

The one free source that natively returns all three data points in one vendor:

- **Location + description + price** in one API: discovery by city / coordinates, static content
  (name, description, amenities, coordinates, photos), and real rates.
- **Free sandbox key, no credit card** (dashboard.liteapi.travel, API Keys tab, `sand_` prefix).
  A live/`prod_` key is issued from the same dashboard. Auth is the `X-API-Key` header.
- Docs: `docs.liteapi.travel`. Config: env `LITEAPI_API_KEY` (see `config.md`, `.env`).
- **Two calls to cover M1:** `GET /v3.0/data/hotels?countryCode=..&cityName=..` (discovery, and
  content comes back in the same payload) then `POST /v3.0/hotels/rates` with the returned
  `hotelIds` (real prices per room/board, with a refundable flag and an `offerId`/`rateId`).
- **Booking flow (deferred, not for M1):** LiteAPI also supports prebook, book, retrieve, and
  cancel, keyed off the rate `offerId`. Recorded here so it is not lost; **out of scope for M1**,
  which is read-only recommendation. See `roadmap.md` → out of scope.
- **Status: VERIFIED live 2026-07-10** (sandbox key). One `data/hotels` call for Barcelona
  returned real hotels with id, name, full description, coordinates, address, photos, stars,
  guest rating, and review count; `hotels/rates` returned real per-hotel prices (e.g. Acta
  Voraport 3-star at 251.61 EUR for 3 nights / 2 adults, up to Olivia Plaza at 743.58 EUR). This
  clears the M1 bar (location + description + price, free, one vendor).

### LiteAPI to domain mapping (M1)

- `rating` (0-10 guest score) maps straight to `Hotel.rating` (kept 0-10, booking.com style);
  `stars` (1-5) to `Hotel.star_rating`; `hotelDescription` to `Hotel.description`; coordinates and
  address as given; `facilityIds` mapped onto the `Amenity` vocabulary (`domain-model.md`).
- Prices: from `POST hotels/rates`, per hotel take the **cheapest refundable** and the **cheapest
  non-refundable** rate (or only the kind set by `filters.refundable`), each becoming a `RateOffer`
  (see `contract.md`). Board and refundable flag carry through.
- Lodging types: all types by default (hotels, hostels, guesthouses, apartments);
  `filters.property_types` narrows.

## Evaluated candidates (2026-07-10 research)

Legend: y = yes, ~ = partial/thin, n = no.

### Group A: one source, all three (location + description + price)

| Source | Loc | Desc | Price | Free terms | Notes |
|---|---|---|---|---|---|
| **LiteAPI (Nuitée)** | y | y | y (real rates) | Free sandbox key, no card; `X-API-Key` | **Chosen for M1.** 2M+ properties, hotels + broader lodging. |
| Amadeus Self-Service | y | ~ | y (real GDS) | Free monthly test quota, OAuth | Coverage skews to chains / big cities; weak on independents and rentals. Candidate later price cross-check. |
| Xotelo (TripAdvisor) | y | ~ | y (multi-OTA) | Free, no key | **Discovery gap:** see live findings. Only a price layer, not standalone. |

### Group B: free + broad, but location + description only (no price)

| Source | Free terms | Notes |
|---|---|---|
| OSM Overpass + Nominatim | Free, no key | Real names, coordinates, lodging type, star tags. No price / rating / real description. Best raw coverage. Needs a `User-Agent` header. Good keyless breadth layer / fallback. |
| Geoapify Places | Free key, 3,000 req/day | Name, address, category (`accommodation.*`). No price, thin description. |
| OpenTripMap | Free key | Strong descriptions (Wikipedia extracts) + images + coordinates. No price. Non-commercial use only. |

### Group C: price-focused only

| Source | Free terms | Notes |
|---|---|---|
| Makcorps / HotelAPI.co | ~30 calls / 30-day trial, then paid | Live + historical OTA prices (Booking / Expedia). Demo-only, not sustained. |

### Vacation rentals / Airbnb

No free production-grade API. Unofficial RapidAPI scrapers have flaky free tiers. Only free static
option is **Inside Airbnb** (quarterly CSV dumps, major cities only, no live endpoint).

## Live-test findings (2026-07-10)

- **OSM Overpass + Nominatim:** works key-free, returns real Barcelona lodging. Requires a proper
  `User-Agent` header (a bare request 406s / rate-limits).
- **Xotelo:** `/rates` works key-free and returns **real multi-OTA prices** (Booking.com, Agoda,
  Trip.com, Official Site) for a known `hotel_key` (`g<geo>-d<detail>` from a TripAdvisor URL).
  But `/search` returns **401 (RapidAPI only)** and `/list` returns **400** on the free host, so
  hotel **discovery by location is not available free**. Usable only as a price layer once a hotel
  is already mapped to its TripAdvisor key.
- **LiteAPI:** pending sandbox-key verification (Barcelona discovery + content + rates).

## Future direction (post-M1)

The provider architecture (`providers.md`) supports running multiple sources. Combinations to
revisit as later batches, and the fallback if LiteAPI's free tier disappoints:

- **OSM** as a free, keyless breadth layer or fallback when LiteAPI coverage is thin.
- **Amadeus test tier** or **Xotelo `/rates`** as an independent price cross-check.
- **OpenTripMap** or the Nebius LLM for richer descriptions.
- **LLM web search** as a backup source (see `roadmap.md`; chat completions do not browse, so it
  needs a separate search tool/API).
