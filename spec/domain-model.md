# Domain model (`models.py`)

The canonical types every other layer speaks. Adapters normalize raw provider payloads into
these; filtering and scoring compare against them. The request/response types built on top live
in `contract.md`.

## `Hotel`

Pydantic model, `extra="forbid"`. **Most fields are optional**, since a scraper may lack a band
or a price:

- `id`, `source` (provenance), `name`
- `location: GeoPoint | None`, `area`, `address`
- `price_per_night`, `currency`, `price_band: PriceBand | None`
- `rating` (guest review score, **0 to 10**, booking.com style), `review_count`,
  `star_rating` (hotel class, 1 to 5)
- `amenities: set[Amenity]`
- `url`, `image_url` (provider-supplied photo, e.g. LiteAPI `main_photo` / `thumbnail`; `None`
  when the provider has none, mock especially), `description` (free text the LLM reads for
  "character")
- `raw: dict` (original payload), `sources: list[str]` (provenance; grows on dedupe)

A model validator guarantees `source` is always present in `sources`.

## `GeoPoint`

Frozen `{lat, lon}` with range validation. Distance math against it is centralized in
`utils/geo.py` (`haversine`), which is the only distance code in the system.

## `PriceBand`

`StrEnum`: `budget | midrange | upscale | luxury`. Derivation of a band from a bare price is a
**global policy** (config cutoffs applied in the pipeline), not per-adapter work: see
`config.md` and `pipeline.md`.

## `Amenity` and normalization

`Amenity` is a `StrEnum`, the controlled vocabulary: `wifi, pool, gym, breakfast, parking, ac,
spa, pet_friendly, kitchen, bar, restaurant, airport_shuttle`.

Helpers `normalize_amenity(str)` and `normalize_amenities(iterable)` map raw provider strings
(including synonyms like "Free WiFi", "Air conditioning", "Garage") onto the vocab and drop
unknowns. **Adapters call these** (see `providers.md`); filtering and scoring compare against
the vocab, never raw strings.
