# intensive.dance

A worldwide register of **intensive courses and master classes** for **classical** and **contemporary ballet**, scraped from the schools and companies that run them.

> Working name. First milestone: scrape intensives into our DB. Nothing user-facing yet.

## What we collect

For every intensive / master class we care about:

- **Time range** — when it runs (start/end, plus the year's "season")
- **Organization** — the school or company hosting it
- **Teachers** — who teaches, and *where they actually teach and dance* (their affiliations)
- **Prices** — tuition and what's included, in the local currency
- **Application deadlines**
- **Application requirements** — none · photos in defined poses · video (specific or open brief) · CV · headshots/portraits

## Provider register

We maintain a register of providers to scrape, weighted toward the marquee names in the genre — e.g. The Royal Ballet School, John Cranko School, ABT (JKO School), Joffrey Ballet School, l'École de Danse de l'Opéra de Paris, English National Ballet School, Bolshoi Ballet Academy.

See [`providers.json`](./providers.json) for the seed list and [`docs/data-model.md`](./docs/data-model.md) for the record shape.

## Stack

Python, mirroring museumsufer's ethos (pure-function scrapers, a deterministic data file committed to git, a cron → single-commit workflow) but stripped to a single page.

- **`uv`** — deps + venv
- **`httpx`** — fetching, with an optional pass-through proxy (`FETCH_PROXY_URL` / `FETCH_PROXY_TOKEN`)
- **`selectolax`** — HTML parsing
- **`pydantic`** v2 — the [data model](./docs/data-model.md) as validated models; the `application.requirements` discriminated union is enforced at parse time

```
src/intensive_dance/
  models.py                 # Pydantic models == docs/data-model.md (source of truth)
  fetch.py                  # httpx client (UA + optional proxy)
  scrapers/                 # one pure fn per provider: scrape(client) -> list[Offering]
  run.py                    # scrape -> hash -> write data/<slug>.json
  validate.py               # offline check: committed data parses + hashes match
  schema.py                 # derive/verify schema/offering.schema.json from the models
data/<slug>.json            # the store: committed JSON, one file per provider
schema/offering.schema.json # published JSON Schema for one Offering (CI guards drift)
tests/                      # pytest: pins the regex-heavy parsing, no network
```

Validation is enforced at model construction (Pydantic) when a scraper builds an `Offering`; `validate.py` re-checks the committed store offline in CI.

### Scraping approach — API first

For each provider, try structured sources **before** parsing HTML. Order of preference:

1. **Official / site-powering JSON API** — e.g. a WordPress REST API (`/wp-json/wp/v2/`), a store API, or any documented endpoint
2. **Structured data embedded in the page** — `<script type="application/ld+json">` (schema.org `Event`/`Course`), or an embedded state blob (`__NEXT_DATA__`, etc.)
3. **Machine-readable feeds** — iCal (`.ics`), RSS/Atom
4. **HTML parsing** (`selectolax`) — last resort

Record which source a scraper uses in a comment, so the next person knows whether to look for an API before touching markup.

Run it:

```bash
uv run python -m intensive_dance.run                    # all providers
uv run python -m intensive_dance.run royal-ballet-school # one provider
```

Store is committed JSON (`data/`) for now — every scrape is a reviewable git diff. Pydantic serializes unchanged if we later swap in SQLite/Postgres.

Dev setup — enable the commit hook once per clone (formats, lints and type-checks with the project's own ruff/ty, the same checks CI runs):

```bash
uv sync                      # installs dev tools, incl. pre-commit
uv run pre-commit install    # ruff format + ruff check + ty on every commit
```

## Status

The register is built out continuously — see [`providers.json`](./providers.json) for every provider and its `seed`/`live` status, and [`data/`](./data) for one JSON file per live provider (an hourly cron keeps them fresh).

A few representative scrapers, each exercising a distinct part of the data model:

- **The Royal Ballet School** ([#1](https://github.com/boredland/intensive-dance/issues/1)) — WordPress REST + WPBakery; exercises the `photos` requirement.
- **Joffrey Ballet School** — WordPress custom post types (`summer-intensives`, `workshops`) + taxonomy resolution; exercises the `video` requirement. Fees/teachers aren't published in its API, so those stay empty (documented in the scraper).
- **Russian Masters Ballet** — the first **pure-HTML** scrape (a Bitrix site, no API/feed/JSON-LD). Discovers its summer (Alicante, Burgas, St. Petersburg) and winter (Madrid, Perth, Shanghai) locations from the two course indexes and emits one offering per program track. First to exercise **teachers with affiliations** (a named per-track roster linked to Vaganova / Bolshoi / Mariinsky / …) and the `video`/`specific` + `cv` requirement branches.
- **MOSA Ballet School** (Liège, BE) — first European provider; a Squarespace site scraped **sitemap-first** (the sitemap indexes every event; we keep only real intensives/masterclasses and drop past cycles). Exercises EUR course-fee parsing.
- **John Cranko School** (Stuttgart, DE) — its Summer School, from one tidy German page; exercises a EUR fee (incl. performance), an application `deadline`, and a `video`/`specific` audition brief.
- **Frankfurt Ballet Masterclasses** (Frankfurt, DE) — single-page masterclass listing; fetched over a `verify=False` client because the host serves an incomplete TLS certificate chain.
- **Dutch National Ballet Academy** (Amsterdam, NL) — its Amsterdam International Summer School (Senior + Junior courses), from the AHK TYPO3 site; one offering per course with its own age band and fee.
- **École de Danse de l'Opéra national de Paris** (Paris, FR) — its Summer School ("Stage d'été"), read off the large operadeparis.fr site; exercises a non-refundable application-fee note (graduated course fees left out rather than guessed).
- **English National Ballet School** (London, GB) ([#19](https://github.com/boredland/intensive-dance/issues/19)) — its Summer Intensives, from a WordPress REST page whose WPBakery layout groups the course titles apart from their details, so the three courses are split out of the page text (one offering each, past cycles dropped); exercises a shared course fee + non-refundable application fee across sibling offerings.
