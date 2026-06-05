# AGENTS.md

Playbook for adding scrapers to **intensive.dance** — a register of classical &
contemporary ballet *intensives / master classes*, scraped into a committed JSON
store. Read this before writing a new scraper; it captures the conventions and
the traps that aren't obvious from one file.

Source-of-truth docs to keep open: [`docs/data-model.md`](./docs/data-model.md)
(record shape) and [`README.md`](./README.md) (project ethos + API-first order).

> **Keep this file current.** This doc is only useful if it stays true. In
> **every PR**, if you learned something significant (a new source shape, a trap,
> a better pattern) or noticed something here is now **outdated, wrong, or
> redundant**, update `AGENTS.md` in the same PR. Prefer correcting/condensing an
> existing line over appending a new one — fight bloat. Treat it as part of the
> change, not a follow-up.

---

## TL;DR — adding a provider

1. Pick a provider that's `"status": "seed"` in [`providers.json`](./providers.json).
2. **Probe API-first** (see decision tree below) before touching HTML.
3. Write `src/intensive_dance/scrapers/<slug_with_underscores>.py` exposing
   `scrape(client) -> list[Offering]`, with the network in `scrape` and all
   parsing in a pure, testable `_build_offerings(payload, today)` + small helpers.
4. Register it in `src/intensive_dance/scrapers/__init__.py` (import + `SCRAPERS`).
5. Flip the provider's `status` to `"live"` in `providers.json`.
6. Add `tests/test_<slug>.py` — inline snippets, **no network**.
7. Generate data: `uv run python -m intensive_dance.run <slug>` → `data/<slug>.json`.
8. Run the full gate (below). All green, then commit on a branch, push, open a PR.

---

## Commands (these are the CI gate — run all before pushing)

```bash
uv sync                                         # deps + dev tools (first time)
uv run pre-commit install                       # optional: run the gate on commit

uv run python -m intensive_dance.run <slug>     # scrape one provider → data/<slug>.json
uv run python -m intensive_dance.run            # all providers

uv run ruff check .                             # lint
uv run ruff format .                            # format (CI checks with --check)
uv run ty check                                 # type-check — WHOLE REPO, incl. tests
uv run pytest -q                                # tests (no network)
uv run python -m intensive_dance.schema         # schema in sync with models?
uv run python -m intensive_dance.validate       # committed data parses + hashes match
```

CI (`.github/workflows/ci.yml`) runs exactly these. A daily cron
(`scrape.yml`) re-runs all scrapers and commits the data diff.

Always use `uv` (never bare `pip`/`python`). `ruff` line-length is **100**.

---

## Project map

```
src/intensive_dance/
  models.py        # Pydantic v2 == docs/data-model.md. THE source of truth.
  parse.py         # provider-agnostic text/date/money/genre helpers
  wp.py            # WordPress REST + WPBakery helpers (for WP-powered providers)
  fetch.py         # make_client(): httpx client w/ UA + optional proxy
  scrapers/        # one module per provider: scrape(client) -> list[Offering]
    __init__.py    # the SCRAPERS registry (slug -> scrape fn)
  run.py           # scrape -> hash -> write data/<slug>.json (deterministic)
  validate.py      # offline: every data/*.json parses + source.hash matches
  schema.py        # derive/drift-check schema/offering.schema.json from models
data/<slug>.json   # the store — committed, one file per provider
providers.json     # the register; each has status seed|live
tests/             # pytest, inline HTML/JSON snippets, no network
```

---

## API-first decision tree (README order, with what we've actually hit)

Try structured sources **before** HTML, and record which you used in the
module docstring so the next person doesn't re-investigate:

1. **Official / site JSON API.** Most ballet schools run **WordPress** →
   `GET {base}/wp-json/` (200 == WP). Use `wp.py`:
   - Programs as **custom post types** (e.g. Joffrey's `summer-intensives`,
     `workshops`, `master-class`) — the clean case: `wp.fetch_all(...)`,
     resolve taxonomy ids with `wp.fetch_terms(...)`. **No HTML at all.**
   - Page bodies in `content.rendered` as WPBakery shortcodes → `wp.parse()`
     turns them into heading-keyed `Section`s; `Content.find/link/table`.
   - **Trap (ABT):** WordPress can still be useless via REST — a custom
     module/ACF page builder may render *nothing* into `content.rendered` and
     expose only module *names*. Confirm the body is actually present before
     committing to API-first; otherwise fall through to HTML.
2. **Embedded structured data** — `<script type="application/ld+json">`
   (schema.org `Event`/`Course`), or a state blob (`__NEXT_DATA__`).
3. **Feeds** — iCal `.ics`, RSS/Atom.
4. **HTML parsing (`selectolax`)** — last resort. Read the page structurally
   (stable class names / table headers), not by brittle absolute position.

---

## Scraper anatomy (mirror an existing one)

- **WordPress-API example:** `scrapers/joffrey_ballet_school.py`
- **HTML, multi-site/track split:** `scrapers/russian_masters_ballet.py`,
  `scrapers/abt_jko_school.py`
- **Single-page HTML:** `scrapers/frankfurt_ballet_masterclasses.py`

Shape every scraper this way so parsing is testable without a network:

```python
def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE); resp.raise_for_status()
    return _build_offerings(resp.text, date.today())

def _build_offerings(html: str, today: date) -> list[Offering]:
    ...  # pure: HTML/JSON in, Offerings out. Tests call THIS.
```

Keep small, single-purpose helpers (`_dates`, `_age_range`, `_prices`,
`_location`, `_levels`, `_genres`, `_requirements`) — tests pin each one.

### Module docstring is required content, not decoration

Every existing scraper opens with: **API FIRST** (what you found / why HTML),
**DISCOVERY** (how programs map to Offerings — one per what?), and **WHAT THIS
SCRAPER EXERCISES** (which model branches, *"verified live YYYY-MM-DD"*). Match
that — it's how the next agent knows the source's shape without re-crawling.

---

## Data model essentials (`models.py` is authoritative)

- **`Offering`** = one offering of an intensive **in a specific cycle**.
  `id = "{provider-slug}/{offering-slug}"`. When a provider runs the same thing
  in several places or tracks, **emit one Offering per place/track** (don't
  fold — you'd lose distinct dates/ages/fees/requirements). Year-stamp the slug
  only when the source distinguishes cycles by year (RMB does; Joffrey reuses an
  evergreen slug, so doesn't).
- **`application.requirements`** is a discriminated union on `type`:
  `none` · `photos` (`defined-poses`/`freeform`) · `video` (`specific`/`unspecific`)
  · `cv` · `headshot`. `[]` = unknown/not stated; `[NoneReq]` = explicitly nothing.
  An audition that accepts an in-person *or* video submission → `video`/`unspecific`.
- **Be faithful, fail open.** Only set a field the source states. Don't invent
  `application.status`/`deadline`; `None` means "not stated". Leave `start/end`
  null and `season` `"unknown"` rather than guessing. Discovery (what's listed),
  not date-parsing, decides what's emitted.
- **Prices** carry a `currency` (ISO 4217) in the **local** currency and an
  `includes` list (`tuition`/`accommodation`/`meals`/…). A provider can have
  several `Price`s per Offering (e.g. tuition + room & board).
- **`age_range`** is `{"min": int, "max": int}` (a bound may be null = open-ended).
- **Determinism / hashing:** `run.py` writes sorted-key JSON and sets
  `source.hash = content_hash()` (which **excludes** `source`), and reuses the
  prior `scrapedAt` when the hash is unchanged — so a no-op re-scrape yields **no
  git diff**. Don't put volatile data in fields; that's the whole point.
- If you change `models.py`, regenerate the schema:
  `uv run python -m intensive_dance.schema --write` (CI fails on drift).

---

## Shared helpers — use them, don't reinvent

- `parse.clean(text)` — collapse whitespace / nbsp.
- `parse.parse_amount("1,400" | "1.299,00" | "12,50")` — currency-notation-aware → float.
- `parse.MONTHS` / `parse.MONTHALT` — English month map + regex alternation for
  date patterns. (`parse.months_alt(...)` to build a non-English one, e.g. German.)
- `parse.match_genres(text, table, default=[...])` — keyword → genre list.
- `wp.*` — `fetch_page`, `fetch_all` (paginates `X-WP-TotalPages`), `fetch_terms`,
  `fetch_children`, `parse()` → `Content`/`Section`, `table_rows`, `node_lines`,
  `button_links`. Use `wp` for **any** WordPress provider.
- `fetch.make_client(verify=False)` — only when a host serves a broken TLS chain
  (Frankfurt does); document why in the scraper.

Date-range and genre-keyword regexes stay **local to each scraper** — their
shapes diverge too much to share. Lift something into `parse.py`/`wp.py` only
when a second provider genuinely needs the identical thing.

---

## Conventions & traps (learned the hard way)

- **`ty check` runs over the whole repo, including `tests/`.** A field typed
  `X | None` (e.g. `Offering.location: Location | None`) will fail
  `attr` access in a test — narrow it first: `assert o.location is not None`
  before `o.location.venue`. (Running `ty check` on one file hides this; always
  run it bare.)
- **Tests never hit the network.** Feed `_build_offerings`/helpers inline HTML or
  JSON snippets covering the real structure (one happy site + one edge: extra
  fees, missing dates, out-of-scope genre…). See `tests/test_abt_jko_school.py`.
- **Parse structurally.** Match table cells by **header text**, not column index;
  read venue/city from address `<p>` lines, not a collapsed string (collapsing
  glued a street number onto the city in the first ABT pass).
- **Drop out-of-scope rows** (Tap/Hip-Hop/etc. for a *ballet* register) and
  cancelled cycles; don't emit empty-genre Offerings.
- **Comments explain *why*, not *what*** (see the global commenting rules). The
  scraper docstrings carry the source-shape reasoning.
- **Git:** work on a branch; commit + push; open a PR with `gh`. **No
  `Co-Authored-By`/attribution lines** in commit messages. Use the DeepL MCP for
  any translation, never translate inline.

---

## Done checklist

- [ ] `scrape` thin (network only); parsing pure + helper-sized
- [ ] Registered in `scrapers/__init__.py`; `providers.json` status → `live`
- [ ] `tests/test_<slug>.py` added, offline, covers the edge cases
- [ ] `data/<slug>.json` generated and looks right (spot-check dates/prices/location)
- [ ] `ruff check .` · `ruff format .` · `ty check` · `pytest -q` · `schema` · `validate` all green
- [ ] Module docstring: API-FIRST + DISCOVERY + WHAT IT EXERCISES (verified date)
- [ ] `AGENTS.md` updated if you learned something / found something stale (see top)
- [ ] Branch → push → PR
