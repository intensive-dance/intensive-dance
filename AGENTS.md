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

## Scope & coordination (read first)

- **We say "scraper", not "crawler"** — these modules *extract* from known pages; they don't crawl/discover the open web.
- **In scope:** short-term **student intensives** (summer schools, intensives, short courses, master classes) — one `Offering` per dated edition.
- **Stub, don't fake:** if a provider is a **full-time vocational school / long-term _Ausbildung_ only** (no public short-term intensive), do NOT invent an offering — leave it `seed`, relabel its issue `phase-2`, defer to **IDR-9 (#12)** (e.g. Elmhurst #79).
- **Competitions are OUT OF SCOPE (icebox).** Prix de Lausanne, YAGP, Tanzolymp, HIBC, … are parked in epic **#80 (IDR-40)** — idea-collection OK, **no implementation**. About to build one? Stop — it's parked on purpose; reopen the discussion first.
- **Coordinate — people work in parallel.** Always `git fetch` + check `gh pr list` / `gh issue list` first. Before building a provider, **create its issue and self-assign** so two people don't build the same one.

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
uv run python -m intensive_dance.erd            # ERD (docs/erd.md) in sync with models?
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
  erd.py           # derive/drift-check docs/erd.md (Mermaid ERD) from models
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

## Fetch proxy (datacenter-IP / broken-TLS / bot-protected pages)

When a host blocks the CI runner's datacenter IP, serves a broken TLS chain, or
gates content behind a **Cloudflare** challenge / **Turnstile** / JS render — a
direct httpx fetch returns a challenge or empty page, not the real markup — route
the request through the fetch proxy instead of giving up. It's a last resort
(slower, rate-limited), so reach for it only after the API-first tree and a plain
fetch have failed, and say in the scraper docstring *why* it was needed.

One service, reached through its **REST `?url=` interface**. `make_client()`
(`src/intensive_dance/fetch.py`) routes every scraper through it via a small
transport when `FETCH_PROXY_URL`/`FETCH_PROXY_TOKEN` are set — you still call
`client.get(real_url)`; the transport rewrites it to `{base}?url=<real>` with
`Authorization: Bearer` and the proxy fetches it server-side (auto-escalating a
block to a stealth Chromium render). It forwards `Accept-Language`, so a scraper
can **pin the render locale** by passing `headers={"Accept-Language": "en"}` —
needed when a localized site serves a translated `og:title`/text under the
proxy's default `de-DE` render (see `mosa_ballet_school`). The query params below
(`render=1`, `wait=…`, `format=md`, …) are the manual escalation tier; there's no
helper, so call the endpoint by hand when a plain proxied fetch comes back blocked.

> **Trap:** a `*.xml` (e.g. a `sitemap.xml` the proxy had to escalate) can come
> back wrapped in Chromium's **XML-viewer HTML**, so `ET.fromstring` chokes. The
> stealth-render tier now returns the *raw* body for non-HTML content-types, so
> this only bites when the escalation goes through the **FlareSolverr/CF-challenge
> tier** (which hands back the rendered DOM) — depends on how the host blocks. The
> URLs survive verbatim either way, so regex them out of the text rather than
> XML-parsing (robust to raw XML *and* the wrapper; see
> `mosa_ballet_school._parse_event_urls`).

**One endpoint** (`/`, GET — or POST to forward the request body + Content-Type
upstream for form POSTs). The base does a plain Chrome-UA fetch with TLS
verification off (covers datacenter-IP blocks and broken certs); query params
escalate from there:

```
$FETCH_PROXY_URL?url=<url-encoded>&auto=1&format=md
```

with `Authorization: Bearer $FETCH_PROXY_TOKEN`. Query params (all optional
except `url`):

| param | effect |
|-------|--------|
| `url` | **Required.** Target URL to fetch (url-encoded). |
| `auto=1` | Auto-escalate `plain → FlareSolverr → stealth render`, returning the first tier that isn't blocked. Prefer this over guessing a tier. `auto=0` opts out if the server defaults it on. |
| `solve=1` | Force the **FlareSolverr** (Cloudflare-challenge solver) path even when the CF heuristic doesn't fire. |
| `render=1` | Return the page rendered by a stealth headless Chromium (for JS/SPA content). |
| `wait=<ms>` | With `render=1`, ms to let the SPA's XHR content settle. Default `6000`, max `30000`. |
| `format=md` | Convert the HTML to Markdown via Readability main-content extraction (nav/ads dropped, links absolutized). Omit for raw HTML. |
| `block=0` | Ad/cookie/tracker blocking (uBO-style filter lists) is **on by default** for rendered pages; set `0` to disable it for this request. |

Full spec: `$FETCH_PROXY_URL/docs` (Scalar UI; raw at `/docs/json`).

**Config — `FETCH_PROXY_URL` + `FETCH_PROXY_TOKEN`.** Both are stored in GitHub
two ways: as **Actions variables** (read in **development**) and as **Actions
secrets** (read in **CI**). Locally, hydrate from the variables — `export
FETCH_PROXY_URL=$(gh variable get FETCH_PROXY_URL)` and `export
FETCH_PROXY_TOKEN=$(gh variable get FETCH_PROXY_TOKEN)`; the `scrape.yml`
workflow injects the `${{ secrets.* }}` equivalents. Never hardcode the proxy
URL or bearer in source.

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
- **Keep ended cycles — don't filter on dates.** A cycle whose `schedule.end`
  is in the past stays in the store; **"past" is derived consumer-side** from
  `schedule.end < today`, never stored (it's not a `lifecycle` value either —
  that enum is `scheduled`/`cancelled`/`postponed`). Families still find a course
  that already ran, and a no-op re-scrape keeps yielding no diff. This is the
  deliberate IDR-24 design (see `fondazione_monreart`, `royal_ballet_school`,
  `russian_masters_ballet`); it **overrides any per-issue AC that says "drop
  already-ended cycles."** Cancelled cycles are likewise kept, tagged
  `lifecycle="cancelled"`, not dropped. (Out-of-scope *genres* and rows the source
  itself removed are still dropped — that's discovery, not a date cut.)
- **Prices** carry a `currency` (ISO 4217) in the **local** currency and an
  `includes` list (`tuition`/`accommodation`/`meals`/…). A provider can have
  several `Price`s per Offering (e.g. tuition + room & board).
- **`age_range`** is `{"min": int, "max": int}` (a bound may be null = open-ended).
- **Determinism / hashing:** `run.py` writes sorted-key JSON and sets
  `source.hash = content_hash()` (which **excludes** `source`), and reuses the
  prior `scrapedAt` when the hash is unchanged — so a no-op re-scrape yields **no
  git diff**. Don't put volatile data in fields; that's the whole point.
- If you change `models.py`, regenerate **both** derived artifacts (CI fails on drift):
  `uv run python -m intensive_dance.schema --write` and
  `uv run python -m intensive_dance.erd --write` (the Mermaid ERD in `docs/erd.md`).

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
  run it bare.) The `[tool.ty]` block in `pyproject.toml` makes it **strict**:
  warnings are errors (`error-on-warning`) and a few latent-bug rules ty leaves
  off (`possibly-missing-import`/`-attribute`, `possibly-unresolved-reference`)
  are on — so a "maybe unbound / maybe missing" path fails the gate, not runtime.
- **Tests never hit the network.** Feed `_build_offerings`/helpers inline HTML or
  JSON snippets covering the real structure (one happy site + one edge: extra
  fees, missing dates, out-of-scope genre…). See `tests/test_abt_jko_school.py`.
- **Parse structurally.** Match table cells by **header text**, not column index;
  read venue/city from address `<p>` lines, not a collapsed string (collapsing
  glued a street number onto the city in the first ABT pass).
- **Match genre keywords against the curriculum list, not loose prose.** A blurb
  can mention "contemporary works" without a Contemporary *class* — keyword-match
  the syllabus headings (SAB's `<h3>` curriculum list) so the description doesn't
  leak a genre the program doesn't teach. Likewise scope level keywords to the
  admission sentence so "the most advanced girls" doesn't read as an advanced
  program. See `scrapers/school_of_american_ballet.py` (two pages, one template).
- **Drop out-of-scope rows** (Tap/Hip-Hop/etc. for a *ballet* register) and
  cancelled cycles; don't emit empty-genre Offerings.
- **Comments explain *why*, not *what*** (see the global commenting rules). The
  scraper docstrings carry the source-shape reasoning.
- **Wix sites are server-rendered** (content is in the static HTML, no JS) but
  pepper the markup with **zero-width spaces** (splitting "€740", gluing a name
  to the next heading) and **letter-space** inline form labels ("a rabesque").
  Strip the zero-width chars and detect requirement *keywords* rather than scrape
  the garbled tokens (see `brussels_international_ballet`, `young_stars_ballet`).
- **Multilingual sites can flip language by cache.** Monreart's `/en/` pages
  serve EN or IT depending on the Varnish cache (even `Accept-Language` doesn't
  pin it), so a naive parse is non-deterministic. Parse **language-agnostically**:
  numeric dates (EN+IT month map), enum genres, numeric ages/prices, title from
  the API, and emit only canonical-English free text — verify EN==IT, never rely
  on one render (see `fondazione_monreart`).
- **Japanese pages: year-less date lines + school-grade ages.** A JP listing
  often gives the course span with no year ("8月6日(木)、…、9日(日)") — read the year
  from the title stamp ("夏休み特別講習会2026") and apply it to the month/day span and
  the deadline. Ages are stated as **school grades**, not numbers: map them by the
  statutory April-entry schedule (小N年→age 6+N…7+N, 中N年→12+N…13+N, 高N年→15+N…16+N)
  and keep the raw grade band verbatim in the session `notes`. Classes that differ
  only by age/gender (not dates/fee) are **one Offering with one `Session` per
  class** (gender only exists on `Session`) — see `tokyo_ballet_school`.
- **One org, several city editions = one scraper, many Offerings.** A provider
  can run the same course as separate per-city subdomains (ART of's
  `zurich.`/`madrid.art-of.net`, same director). Build **one** scraper filed
  under one slug that emits one Offering per city (distinct dates/ages/venue/
  currency), and collapse the duplicate `providers.json` rows — remove the
  redundant `seed` entries so nobody double-builds (see
  `art_of_ballet_summer_course`).
- **Suppress unverified marquee claims.** Don't launder a provider's marketing
  into the data if you can't verify it — e.g. ART of's "partner of the Prix de
  Lausanne" line is false, so it's omitted entirely (a teacher's own verifiable
  bio credential, by contrast, stays). Faithful ≠ credulous.
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
