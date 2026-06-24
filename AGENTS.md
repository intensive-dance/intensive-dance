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
>
> **Architecture / infra / ops / legal changes also live in the internal doc-set.**
> If a change alters the architecture, infrastructure, operational workflow, data
> model, or legal/compliance posture, mirror it into the **private companion repo's
> `docs/` set** (and regenerate its `viewer.html`) in the **same PR** — same ethos,
> broader than this file. That set (architecture · infra · operations · legal risk
> register) is the PO/architect reference and must not drift.

---

## Scope & coordination (read first)

- **We say "scraper", not "crawler"** — these modules *extract* from known pages; they don't crawl/discover the open web.
- **In scope:** short-term **student intensives** (summer schools, intensives, short courses, master classes) — one `Offering` per dated edition.
- **Stub, don't fake:** if a provider is a **full-time vocational school / long-term _Ausbildung_ only** (no public short-term intensive), do NOT invent an offering — leave it `seed`, relabel its issue `phase-2`, defer to **IDR-9 (#12)**. But **verify before deferring** — a full-time vocational school often *also* sells a public dated summer school (Elmhurst, once cited here as full-time-only #79, in fact runs open Senior/Junior Summer Schools — now `live`). Build the public short course, leave the full-time track out (cf. `escola_bolshoi_brasil`, `elmhurst_ballet_school`).
- **The competition *event* is OUT OF SCOPE (icebox) — but a competition's *intensive* is IN.** The competitions themselves (Prix de Lausanne, YAGP, Tanzolymp, HIBC, …) are parked in epic **#80 (IDR-40)** — idea-collection OK, **no implementation**. But a dated **student intensive / summer school** run under a competition's brand is a normal in-scope provider: build it under its **own intensive slug** (one `Offering` per edition), separate from the competition entry. Precedent: `prix-de-lausanne-summer-intensive` is **live** while `prix-de-lausanne` (the competition) stays excluded; a YAGP- or Varna-hosted intensive would qualify the same way. About to build the *competition* itself? Stop — it's parked on purpose; reopen the discussion first.
- **Coordinate — people work in parallel.** Always `git fetch` + check `gh pr list` / `gh issue list` first. **Claim before you build:** the buildable seeds are [`docs/buildable.md`](./docs/buildable.md) (generated from `providers.json` — `uv run python -m intensive_dance.overview`). To take one, open a `build:<slug>` issue and **self-assign first**, *then* build; close it when the PR merges (provider → `live`). **An open `build:` issue *or* PR for a slug = locked — don't build it.** `providers.json` stays the source of truth; the issue is just a transient lock.
- **Two phases — decide cheaply, then build; the build *is* the evaluation.** Confidence is effectively binary (low until scraped, high after), so don't model this as three boxes (explore → score → build). **Phase 1 (cheap, interactive):** find the provider, write its User Story (issue `IDR-<n>`: source URL, API-first finding, discovery = one `Offering` per *what*?), self-assign it, apply **verify-or-defer**, and do a **light triage** — only enough to answer *"worth building?"*, from what web research alone gives (who runs it, accreditation, reputation, track record). The data-derived facts (the actual roster, real dates/duration, prices, application requirements) aren't available yet — so **don't over-score a lead**; scale effort to the decision's uncertainty (obvious-strong → build queue, obvious-weak → drop, only the marginal ones weighed). **Phase 2 (expensive, batchable):** the scraper is by far the most token-heavy step (parallel agents, live probes, the full gate) **and** the thing that yields the real data — so the genuine evaluation happens *here*, not before. Keep it a separate, deliberate batch (e.g. kicked off overnight); each session stays small. **Never discover→build in one pass for a fresh lead, and never treat a lead's preview numbers as final.**

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
uv run python -m intensive_dance.run --touch <slug>   # + stamp source.attemptedAt (rotation; see below)
uv run python -m intensive_dance.rotation 10    # JSON: 10 least-recently-attempted slugs

uv run ruff check .                             # lint
uv run ruff format .                            # format (CI checks with --check)
uv run ty check                                 # type-check — WHOLE REPO, incl. tests
uv run pytest -q                                # tests (no network)
uv run python -m intensive_dance.schema         # schema in sync with models?
uv run python -m intensive_dance.erd            # ERD (docs/erd.md) in sync with models?
uv run python -m intensive_dance.validate       # committed data parses + hashes match
```

CI (`.github/workflows/ci.yml`) runs exactly these (it skips `data/**`-only
pushes — the hourly scrape commits). An **hourly** cron (`scrape.yml`) picks the
10 least-recently-attempted scrapers (`rotation.select_stale`), runs each as an
independent, `continue-on-error` matrix job (`--touch`), then a single `commit`
job (`if: always()`) collects their artifacts and commits — so one flaky site
never blocks the rest, and a commit always lands (every picked provider's
`attemptedAt` is bumped).

**Self-healing → Copilot.** Two loops hand broken scrapers to the GitHub Copilot
coding agent (one open issue per loop, reused so daily runs don't pile up dupes):
a crashed `scrape.yml` leg uploads a `fail-<slug>` marker that the run's final
`report` job (`intensive_dance.report_failure`) digests into a `scrape-failure`
issue; and `scraper-audit.yml` (daily) flags any **live** provider whose
committed store holds **zero** offerings (`intensive_dance.audit` →
`assign_audit`, exempt via `audit_allowlist.json`) into a `scraper-audit` issue.
**Token split (don't merge it back):** issue/label ops and the run-log read run
on the job's default `GITHUB_TOKEN` (`issues: write` + `actions: read`); only the
Copilot assignment uses a user PAT — `COPILOT_TOKEN` (← `COPILOT_PAT`/`COPILOT_CLI_TOKEN`),
since the default token can't assign the agent. Assignment goes through the REST
agent-assignment body (`intensive_dance.copilot`) and is **best-effort** — an
absent/under-scoped PAT just skips it; the tracker issue still lands on the
default token. (Funnelling everything through the lone `COPILOT_CLI_TOKEN`, which
lacks Issues scope, used to crash the whole `report` job at `gh label create`.)
These ops scripts are stdlib-only (run with `PYTHONPATH=src python3 -m …`, no `uv sync`).

**Doc-currency → tracker (not Copilot).** A third loop, `doc-audit.yml` (weekly),
guards the *prose* the way CI already guards the derived docs. `intensive_dance.doc_audit`
scans the committed docs for deterministic drift smells — stale `boredland/…`
(pre-org-transfer) repo refs, prose counts that disagree with
`providers.json`/the store by >15% (dated "snapshot"/"as of" lines exempt), and
dead relative Markdown links — and `report_doc_audit` opens/refreshes one reusable
`doc-audit` issue. It is **not** handed to Copilot (doc fixes need editorial
judgement and often span sibling repos); it's a reminder for the PO, needing only
`issues: write` (no Copilot PAT). Per-provider *status* is deliberately **not**
audited — `candidates.md` is a historical discovery record; `providers.json` is the
truth (so don't restate status in prose; link it).

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
  validate.py      # offline: every data/*.json parses + source.hash matches (+ gazetteer parses)
  schema.py        # derive/drift-check schema/offering.schema.json from models
  erd.py           # derive/drift-check docs/erd.md (Mermaid ERD) from models
  geo.py           # PURE gazetteer half: model, (country,city)->coords load/save, haversine, coverage
  geocode.py       # NETWORK half (hand-run): fill data/gazetteer.json via Nominatim — never in scrape/CI
  bundle.py        # produce the consumer FEED (live offerings + joined coords) for the UI repo
data/<slug>.json   # the store — committed, one file per provider
data/gazetteer.json # committed (country,city)->coords for proximity search (IDR-73); NOT per-provider
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
     committing to API-first; otherwise fall through to HTML. (**Elementor** is
     the same — empty `content.rendered`, and The Events Calendar plugin can hold
     *zero* events; scrape the server-rendered HTML. When only the **home** page
     was updated for the new edition while detail pages (schedule/pricing) carry
     **stale prior-year** content, read the dated edition off the home page and
     **don't borrow** the stale-year course fees onto it — that's inventing data;
     keep only fees the current pages state, e.g. a registration deposit. A
     **single-purpose** intensive site's "Docenti"/faculty page *is* this
     intensive's faculty — safe to attribute, unlike a multi-program school. See
     `bobbio_summer_ballet_intensive`.)
   - **Trap (PBI):** a site the candidate notes call "Wix/JS" can actually be
     plain WordPress (check `/wp-json/`) with clean `content.rendered` bodies and
     **no JS/proxy needed**. But the *dated edition* may live only in the WP site
     description (the home `<title>`, e.g. "… Summer 2026, August 10th – 22nd")
     while the home page's own content block is theme-rendered empty — fetch the
     home HTML for that one string, the API for the rest (see
     `prague_ballet_intensive`).
   - **Trap (SFB):** clean `content.rendered` over `/wp-json/` is *parsing*, not
     *fetching* — a WAF can still 403 our scraper UA on the direct fetch (even of
     `/wp-json/`). The fetch proxy clears it (server-side Chrome UA, **auto tier,
     no render**) — so the proxy is needed for a no-JS API scrape (see
     `san_francisco_ballet_school`).
   - **Trap (Annarella):** a WP install can live in a **subfolder** — the REST
     root is `{base}/site/wp-json/`, not `{base}/wp-json/` (the apex is a
     marketing landing page). Pass `base="…/site"` to `wp.fetch_page`. Also: a
     provider's course *index* can link several editions but only some have a
     real **detail page** — a "Curso de Páscoa" whose page is a bare registration
     form (no genres/ages/dates of its own) is a genre-less stub; **don't emit
     it**, build only the editions whose own page carries the structured detail
     (see `conservatorio_annarella`).
   - **Trap (Coreutica):** an evergreen "Summer Course" *page* can carry only a
     blurb and embed the **dated edition via a WPBakery `vc_basic_grid`** that
     pulls **posts in a category** — read that category's posts directly
     (`wp.fetch_all("posts", params={"categories": <id>})`), one Offering per
     edition. The category name may be generic ("Corso"), so scope by title
     ("estiv" = summer). Those post bodies arrive as **raw, un-rendered WPBakery
     shortcodes** (no `<h*>` headings → `wp.parse` finds nothing): slice the flat
     `[vc_column_text]` blocks and key on the Italian `Label:`/value run. The
     summer course "*doubles as the audition*" for the academy's year-round
     tracks — P1: keep that only as a note, don't import academy-entry rules. And
     `" ".join(some_string)` letter-spaces every character — concatenate strings,
     don't `join` them (see `accademia_internazionale_coreutica`).
   - **Trap (Avada/Fusion):** an Avada/Fusion-themed WP renders **clean
     `content.rendered`** but as plain *HTML* (not WPBakery shortcodes), so
     `wp.parse` (which keys off heading-shortcode structure) buys little — just
     strip tags to flat prose and regex it. Each yearly edition can be its own
     **page** under a stable slug family (`summer-school`, `summer-school-YYYY`):
     discover by `search=` + a `slug.startswith(...)` filter to drop look-alikes
     (a gala, an evergreen overview page). **The page title can lag the body** —
     the current edition's page was titled "Summer School 2023" while its body
     announced the *2024* intensive — so read the year/dates from the body header,
     never the title (see `la_sylphide_ballet_academy`).
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
block to a stealth Chromium render). The transport also **retries transient
gateway blips** (the proxy is Cloudflare-fronted and under load returns 524 /
502 / 503, or times out — `_RetryTransport`, 3 attempts, linear backoff): one
such blip used to fail a whole scraper and spam the scrape-failure tracker with a
fresh random rotation set each hour, so don't read a lone 524 as a scraper bug.
It forwards `Accept-Language`, so a scraper
can **pin the render locale** by passing `headers={"Accept-Language": "en"}` —
needed when a localized site serves a translated `og:title`/text under the
proxy's default `de-DE` render (see `mosa_ballet_school`). The query params below
(`render=1`, `wait=…`, `format=md`, `solve=1`, …) are the manual escalation tier:
pass them per-request via the `PROXY_PARAMS_HEADER` (`fetch.py`) header —
`client.get(url, headers={PROXY_PARAMS_HEADER: "solve=1"})` — and the transport
merges them into the proxy query string (the header is stripped, never forwarded
upstream, and inert on a direct fetch). Needed when the proxy's auto-escalation
doesn't clear a block: a **Cloudflare challenge** can 403 the plain *and* the
`render`/`auto` tiers while only the FlareSolverr `solve=1` tier returns 200 (see
`bolshoi_summer_intensive_tokyo`, which forces `solve=1`).

> **Trap:** a `*.xml` (e.g. a `sitemap.xml` the proxy had to escalate) can come
> back wrapped in Chromium's **XML-viewer HTML**, so `ET.fromstring` chokes. The
> stealth-render tier now returns the *raw* body for non-HTML content-types, so
> this only bites when the escalation goes through the **FlareSolverr/CF-challenge
> tier** (which hands back the rendered DOM) — depends on how the host blocks. The
> URLs survive verbatim either way, so regex them out of the text rather than
> XML-parsing (robust to raw XML *and* the wrapper; see
> `mosa_ballet_school._parse_event_urls`).
>
> **Trap (CF-gated WP REST via `solve=1`):** a Cloudflare-gated WordPress whose
> `/wp-json/` only returns through the FlareSolverr `solve=1` tier comes back the
> same way — the **JSON** wrapped in Chromium's JSON viewer (`<pre>`, HTML-escaped)
> — *and* Cloudflare's email-protection script injects **real** `<a
> class="__cf_email__">` tags into displayed emails, whose unescaped `"` break
> `json.loads`. `wp.fetch_*` (which call `resp.json()`) can't help. Unwrap by hand:
> legit JSON brackets are escaped (`&lt;`/`&gt;`), so the only *real* `<…>` tags
> are CF's injections — `re.sub(r"<[^>]*>","")` them, convert the structural
> entities back (`&lt;`→`<`, `&gt;`→`>`, `&amp;`→`&`, last), then `json.loads`.
> Force the tier with `headers={PROXY_PARAMS_HEADER: "solve=1"}` (see
> `associazione_europea_danza._unwrap`).

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

## LLM access (AI proxy)

Need a model from Python? Hit the **AI proxy** — one OpenAI-compatible endpoint
fronting Copilot/GitHub (`openai/*`), Gemini, and Mistral models. Stock `openai`
SDK:

```python
client = OpenAI(base_url=os.environ["AI_PROXY_URL"], api_key="unused")
client.chat.completions.create(model="gemini-2.5-flash", messages=[...])
```

**Keep it out of the deterministic `scrape()` path** — an LLM call is
non-deterministic and network-bound, so it breaks hashing (a no-op re-scrape must
yield no diff), offline tests, and the never-invent rule. Fine as a **hand-run
dev/enrichment helper** whose output you review and commit as static data; never
in the live scrape/hash path.

**Auth — `AI_PROXY_URL`, same storage pattern as the fetch proxy.** Stored both
ways: an **Actions variable** (dev) and an **Actions secret** (CI). The access
token is **baked into the URL path**, so there's no bearer — `api_key` is unused
(pass any placeholder; the SDK just requires a non-empty string). Locally: `export
AI_PROXY_URL=$(gh variable get AI_PROXY_URL)`. Never hardcode the URL in source.
Model catalog: `GET $AI_PROXY_URL/models` (the list is dynamic — `owned_by` is
`github`/`gemini`/`mistral`). All three work; the `openai/*` Copilot models
occasionally 502 (`AiGatewayError`), so **retry** (or prefer Gemini/Mistral if you
need zero flakes). Smoke test: `.github/workflows/ai-proxy-test.yml`
(`workflow_dispatch`, prints the reply).

**Search grounding — native Gemini endpoint, not the OpenAI surface.** The
OpenAI-compat `/chat/completions` **cannot** ground (every `google_search` tool
shape 400s; an ungrounded flash model returns `null` rather than inventing).
Grounding lives on the proxy's **native Gemini** path — `POST
$AI_PROXY_URL/v1beta/models/<model>:generateContent` with `"tools":
[{"google_search": {}}]`, Gemini-native request body (`contents`/`parts`). Prefer
the **flash / flash-lite** models (`gemini-2.5-flash`, `gemini-flash-latest`,
`gemini-flash-lite-latest`) — fast, cheap, grounding-capable. The response carries
`candidates[0].groundingMetadata` (`webSearchQueries`, `groundingChunks` with
source URLs) — use it to verify the answer is actually sourced, not hallucinated.
**Trap:** the proxy is Cloudflare-fronted and 403s (`error code: 1010`, "browser
banned") on a default urllib/httpx UA — send a normal Chrome `User-Agent` and it
passes (the OpenAI SDK already does; a hand-rolled request must set it). Still a
**dev/enrichment** tool, never the live `scrape()` path. A ready-made grounded-query
helper + a data-correctness review playbook live in the **`data-review` skill**
(`.claude/skills/data-review/`).

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
- **Raise on a degraded fetch; don't return `[]`.** `run.py` writes whatever
  `scrape()` returns — so an empty list **overwrites** a good store with zero
  offerings (and trips the zero-offering audit), whereas an **exception** is
  caught per-provider and the prior store is *kept* (only `attemptedAt` bumps).
  For a single-edition / always-current site, a fetch that returns 200 but lacks
  the expected edition marker (challenge page, partial render) parses to nothing
  — **raise** there rather than emit `[]`, so one transient blip can't wipe the
  committed edition. This pairs with IDR-24 (a removed edition is also better kept
  than emptied). See `bobbio_summer_ballet_intensive` (the "Summer Camp YYYY"
  marker guard, audit #316). Multi-edition discovery scrapers that legitimately
  vary in count are the exception — there `[]` can be real.
- **Prices** carry a `currency` (ISO 4217) in the **local** currency and an
  `includes` list (`tuition`/`accommodation`/`meals`/…). A provider can have
  several `Price`s per Offering (e.g. tuition + room & board).
- **`age_range`** is `{"min": int, "max": int}` (a bound may be null = open-ended).
- **Determinism / hashing:** `run.py` writes sorted-key JSON and sets
  `source.hash = content_hash()` (which **excludes** `source`), and reuses the
  prior `scrapedAt` when the hash is unchanged — so a no-op re-scrape yields **no
  git diff**. Don't put volatile data in fields; that's the whole point.
- **`source.attemptedAt` — the rotation cursor, the one deliberate exception.**
  `scrapedAt` = last content change (no-diff above). `attemptedAt` = last fetch
  *attempt*, and it's **volatile by design**: only `run.py --touch` writes it
  (success *and* failure, via `stamp_attempt`), so plain/dev runs stay no-diff
  (they carry the prior value). It exists because the hourly CI rotation
  (`scrape.yml`) orders providers by it — see `rotation.select_stale`. So a
  `--touch` re-scrape *does* produce an `attemptedAt`-only diff every hour; that
  churn is intentional and overrides the "no-op = no diff" rule **for that field
  only**. Excluded from `content_hash`, so `validate` is unaffected.
- If you change `models.py`, regenerate **both** derived artifacts (CI fails on drift):
  `uv run python -m intensive_dance.schema --write` and
  `uv run python -m intensive_dance.erd --write` (the Mermaid ERD in `docs/erd.md`).
- **Coordinates live in the gazetteer, never in a scraper.** `Location` stays
  `venue/city/country/online` only; the consumer's "intensives near me" join reads
  `data/gazetteer.json` (`(country,city)→coords`). Geocoding is **enrichment** —
  network-bound + non-deterministic, so it's the same rule as the LLM helpers:
  `intensive_dance.geocode` (Nominatim, hand-run, reviewed) fills the gazetteer,
  **never** `scrape()`/CI. `intensive_dance.geo` is the pure half (load/save,
  haversine, coverage). `geo --check` (gap report) is **deliberately not in the
  gate** — a scraper adding a provider in a new city must not block an unrelated
  PR; the consumer falls back to a "location unknown" group and a later `geocode`
  run tops it up. Design: `docs/solution-design-location-search.md` (IDR-73).
- **This repo is the data backend — the customer UI lives elsewhere.** The
  consumer-facing register (HTML/JS) is the **separate private repo
  `ha1des/intensive-dance-ui`**; do NOT add UI here. This repo *publishes a feed*
  it consumes: `intensive_dance.bundle` projects the live store + gazetteer coords
  into one JSON (`bundle --out ../intensive-dance-ui/data.json`, or stdout). The
  feed generator stays here (it owns the data); the page that renders it does not.

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
- **Anchor stop-cue / keyword regexes on word boundaries.** A bare substring cue
  matches *inside* a word: the boilerplate stop `le classi` fired inside "Va**lle
  classi**co" (Della Valle classico), truncating the faculty region to nothing.
  Use `\b…` (and match Italian discipline words like `contemporaneo`, not English
  "Contemporary", so an affiliation name like "London **Contemporary** Dance
  School" can't leak a genre) — see `arteballetto`, a per-year intensive announced
  as plain WP posts (no category): discover by `search` + a title-number filter,
  and keep faculty **names-only** when the prose shape drifts year to year.
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
- **`selectolax` `node.css(tag)` includes the node itself** when the node's
  own tag matches — so `li.css("li")` always yields at least one element (the
  `li` itself), making it useless as a "has child `<li>`" guard. Use
  `li.css_first("ul")` (looks for a descendant `<ul>`) to detect a non-leaf
  list item. Likewise, when a parent `<li>` nests a sub-list, its `.text()`
  collapses all descendants — strip the nested block from the raw HTML
  (`node.html.replace(child.html, "")`) to get just the parent's own text (see
  `orsolina28._tab_prices`).
- **Wix sites are server-rendered** (content is in the static HTML, no JS) but
  pepper the markup with **zero-width spaces** (splitting "€740", gluing a name
  to the next heading) and **letter-space** inline form labels ("a rabesque").
  Strip the zero-width chars and detect requirement *keywords* rather than scrape
  the garbled tokens (see `brussels_international_ballet`, `young_stars_ballet`).
  **Trap — proxy needs `render=1`:** a Wix site can fetch fine *directly* yet
  block the fetch proxy's datacenter egress — the proxy's plain *and* `auto=1`
  tiers time out, only the stealth `render=1` tier returns the page. Since CI
  fetches through the proxy, force `render=1` per-request via `PROXY_PARAMS_HEADER`
  (inert on a direct dev fetch) or the live store silently goes empty (see
  `young_stars_ballet`, `prague_ballet_workshop`).
  **Trap — "copy-page" edition slugs:** a Wix org rolls a new edition by
  *duplicating* last year's pages, so the current detail lives on `kopie-…`
  ("copy") slugs the home menu links to — pin those slugs and re-confirm on
  rollover. Instructor rosters there split each name and its credential across
  separate nodes, so attributing bios/affiliations is unreliable — capture names
  only (filter credential/section lines by keyword; see `prague_ballet_workshop`).
  **Trap — a press-round-up page:** some Wix event pages are mostly years of
  stacked "KEEP READING" article excerpts (prior editions) around one
  current-edition paragraph. Parse **only** that paragraph's date/program and the
  `meta description` summary; the clippings carry stale year/date lines (a "15-27
  luglio" excerpt next to the real "20 luglio 01 agosto 2026") that loose
  whole-page date regexing would mis-pick. Italian spans can be separator-less
  ("20 luglio 01 agosto 2026") — match day-month-day-month-year with a local
  Italian month map (`parse.months_alt`) (see `dance_and_fashion_cic`).
- **Webflow sites are static HTML** (`data-wf-domain`/`cdn.prod.webflow`; no
  `/wp-json/`, no `ld+json`). Course pages render the dated detail as a flat run
  of `Label:` lines ("Dates:", "Where:", "Cost:") — read those, and take the
  programme title from the `og:title` meta. A `Where:` value can carry an internal
  colon (`Te Whaea: National Dance and Drama Centre`) and the labels are separated
  by **zero-width joiners**, so don't stop a venue at the first `:`; bound it on
  the next known label/sentence. Per-programme pages share one template, so an
  *undated* edition still renders ("No items found", a future-year "contact us") —
  emit nothing for it rather than borrow a date from the site calendar (see
  `new_zealand_school_of_dance`).
- **base44 React SPAs render nothing without JS — force `render=1`.** A
  base44-built site (image/asset URLs under `base44.app/api/apps/<id>/…`) has no
  `/wp-json/`, no `Event`/`Course` `ld+json` (only generic SEO meta), and **no
  inline state blob** — the program data is fetched client-side, so the static
  HTML is an empty shell (a sea of `"… manages N data types including inquiries"`
  SEO boilerplate plus a nav listing *every* page incl. builder scaffolds like
  "Business Plan Content"/"Faculty Admin", a tell-tale of an un-launched template).
  Read the stealth-rendered DOM: force `render=1` per-request via
  `PROXY_PARAMS_HEADER`, then parse the rendered text by **stable content strings**
  (React class names are hashed/useless). The real React-Helmet `og:title` carries
  `data-rh="true"` — the bare template default sits alongside it, so pick the
  `data-rh` one. Pricing cards render as `label / "€ amount" / "Deposit to secure:
  € amount"` line triples; faculty as `Name` + a `Title · Company` credential line
  (parse current-vs-former from a `(YYYY–YYYY)` tenure). **Re-verify stale
  deferrals in season:** this provider was excluded "pre-launch — all TBC" months
  ago and by June 2026 had a concrete dated edition — a peak-season re-check
  flipped it back to buildable (see `wiener_ballettakademie`, #362).
- **A bot-gated HTML site can still expose a PDF source.** A provider's HTML and
  `/wp-json/` can sit behind an aggressive bot challenge the proxy's stealth/CF
  tiers clear only intermittently, while a **PDF in its file store** (e.g. the
  `bando`/announcement) fetches reliably through the proxy's plain `auto=1` tier
  (the challenge gates HTML, not the PDF). When the PDF carries the structured
  dates/fees/faculty, scrape *it* (see `teatro_san_carlo_scuola_ballo`).
- **A WP page can be evergreen while the dated edition lives only as a media-library
  PDF.** A WordPress "Workshops" page can have clean `content.rendered` that only
  *describes* the recurring courses (no dates) — the dated editions are uploaded as
  **timetable (Stundenplan) PDFs** in `/wp-json/wp/v2/media`. Query media
  (`?search=<workshop>`), pick the **current edition** by parsing year+revision out
  of the file slug (`Stdplan_Osterworkshop_<year>_<rev>` → latest wins; this is
  discovery, not a date cut — old revisions are superseded artifacts), then PDF-scrape
  it. Dates come from the "DD.MM." day-header row + the slug year (the timetable has
  no year); ages from the "N-M J." / "ab N J." level legend; faculty from the
  LEHRKRÄFTE legend (one `<initials> <Name>` per **raw** line — don't `parse.clean`
  first or the names glue together). Sibling course types may *not* be parseable
  (the SummerWorkshop schedule has no age legend), so scope to the structured one
  (see `benedict_manniegel`).
- **Multilingual sites can flip language by cache.** Monreart's `/en/` pages
  serve EN or IT depending on the Varnish cache (even `Accept-Language` doesn't
  pin it), so a naive parse is non-deterministic. Parse **language-agnostically**:
  numeric dates (EN+IT month map), enum genres, numeric ages/prices, title from
  the API, and emit only canonical-English free text — verify EN==IT, never rely
  on one render (see `fondazione_monreart`).
- **SEOmatic/Craft headless sites: server-rendered HTML, generic ld+json, grade
  ages.** A site whose generator meta is **SEOmatic** (Craft CMS) has no `/wp-json/`
  and its only `ld+json` is generic `WebPage`/`Organization` SEO data (no
  `Event`/`Course`) — but the page is fully server-rendered, so it's a plain
  `selectolax` text scrape. Western grade bands ("Grades 5-8 / 9-12") are the same
  trap as the JP grades: map them to ages (Alberta/most Canada: Grade N ≈ age N+5)
  and keep the raw band in `schedule.notes`. When the *same* intensive runs as two
  **parallel dated sessions** (two 3-week blocks), emit **one Offering per session**
  — a folded 6-week span would misrepresent two distinct 3-week courses (see
  `alberta_ballet_school`).
- **StackProtect/Cloudflare-gated custom (non-WP) sites: proxy `auto=1`, slice the
  accordion, watch nbsp.** A custom-PHP site (no `/wp-json/`, no `Event`/`Course`
  `ld+json`) behind a StackProtect/Cloudflare challenge 403s a plain datacenter
  fetch — the proxy's **`auto=1`** tier clears it and returns the server-rendered
  HTML (no JS `render` needed). The gate clears non-deterministically and
  surfaces a transient **401/403** through the proxy (the surfaced status drifts
  per host/over time — elmhurst moved 403→401, repeatedly tripping the
  scrape-failure tracker: #347/#351/#359/#364); both are in `fetch._RETRY_STATUS`,
  so the shared transport **auto-re-sends** them — the scraper needs no manual
  retry. Course detail lives in Bootstrap accordion panels (`#collapseN`)
  whose sub-programmes split on `<h4>`s. **Trap:** those `<h4>`s carry a
  **non-breaking space** ("Seniors -\xa0(Ages 14–18)"), so a `parse.clean`'d
  heading won't `str.find` inside the raw `panel.text()` — normalize nbsp on
  *both* the text and the heading (keeping newlines for per-line date/fee parsing)
  before slicing (see `elmhurst_ballet_school`). Photograph/Video "requirements"
  pages on such school sites usually belong to the *full-time audition* flow, not
  the summer school — don't attribute them to the short course.
- **TYPO3 sites: plain HTML, `<strong>`-labelled `<p>` fields, dedupe a shared
  course across providers.** A TYPO3 site (no `/wp-json/`, only a generic
  `BreadcrumbList` `ld+json`) is server-rendered — a plain `selectolax` scrape.
  Each program sits in a `div.frame--type-text` whose `<h3>` names it and whose
  `<p>` bodies carry `<strong>Label</strong> value` pairs split by `<br>` (read
  them by splitting each `<p>`'s inner HTML on `<br>` then regexing the
  `<strong>`); a German day span is month-named ("24-29. August 2026" → local
  month map). **Trap — cross-provider duplicate:** when a page lists two parallel
  editions and one is a **named cooperation already built under its own provider**
  (Ballett Dortmund's "Sommerakademie Junior" *is* the `dbft-sommerakademie`
  course on dbft.de), emit only the edition not covered elsewhere — don't ship the
  same intensive twice under two slugs (see `ballett_dortmund`, emits only the
  open Internationale Sommerakademie).
- **A "full-time school" can still sell public short courses.** The Brazilian
  Bolshoi branch is a free full-time vocational school, but it *also* sells dated,
  open-enrollment paid short courses (Cursos de Inverno / Vivências / Workshops) —
  build those, leave the full-time *Ausbildung* out. Booking apps split the
  catalogue across `?tipo=` tabs whose bare default only shows one cohort, so
  **union-crawl the tabs and dedupe on the course id**; read location *per course*
  (pop-up workshops run in other cities), and treat a `min–100` age as
  open-topped (100 = the form's "no max" sentinel). Skip the "para professores"
  teacher-training editions — not student intensives (see `escola_bolshoi_brasil`).
- **A regional company's school summer page = many program-card Offerings, gate
  each on a ballet class.** A pro company's affiliated school (American Midwest
  Ballet) puts its whole summer on one WP page (`content.rendered` over
  `/wp-json/wp/v2/pages?slug=…`, clean) as several program *cards* — a mix of
  recreational and academy-track **short courses**. Emit **one Offering per dated
  card that actually teaches ballet**, slicing the page text by card heading;
  drop the cards with no ballet class (creative-movement-for-3-5, a free "Day of
  Dance" open house) via the empty-genre rule. **Trap:** a card carries both its
  class dates *and* a "Registration deadline: June 1" line, so scope the
  list-of-single-dates extraction to the camp-list sub-segment ("Camps*: …Cost:")
  or the deadline date becomes the start (see `american_midwest_ballet`).
- **Japanese pages: year-less date lines + school-grade ages.** A JP listing
  often gives the course span with no year ("8月6日(木)、…、9日(日)") — read the year
  from the title stamp ("夏休み特別講習会2026") and apply it to the month/day span and
  the deadline. Ages are stated as **school grades**, not numbers: map them by the
  statutory April-entry schedule (小N年→age 6+N…7+N, 中N年→12+N…13+N, 高N年→15+N…16+N)
  and keep the raw grade band verbatim in the session `notes`. An open-ended band
  ("小学3年生～") keeps a **null upper bound**; an Offering spanning such a class
  stays open-topped too. Classes that differ only by age/gender (not dates/fee)
  are **one Offering with one `Session` per class** (gender only exists on
  `Session`) — see `tokyo_ballet_school`, `tokyo_city_ballet`. JP pages also love
  **full-width digits** ("７月２４日") — `str.translate` them to ASCII once up front
  so one date/price regex works; and the year can hide on a *deadline* row
  ("2026年6月20日申請分まで") when the dateline is year-less, while a separate "open
  day" line runs a day past the "から" range close — read both (see
  `dd_masterclass_japan`). A company's short-term workshop can live on a
  **competition microsite** while its school site has no workshop page — scrape
  the dedicated workshop page there, but anchor on its structured 開催概要/受講料
  blocks: such pages keep **stale prior-edition prose** (commented-out 中止 lines,
  past-year admin dates) that loose-text parsing would catch (see
  `tokyo_city_ballet`). An **open-class studio with rotating guests** is mostly
  out of scope (drop-in classes aren't a dated edition), but its recurring,
  *dated* **guest-school workshop-audition** (a visiting school screening dancers
  for 短期留学 short-term study) IS in scope — one Offering per edition. Discover
  these via the WP REST `posts?search=ワークショップ・オーディション`, but **filter
  hard**: keep only the post that IS the workshop (require the structured
  per-school audition band "<school>：N歳-M歳"), and skip (a) pure pro-company
  auditions and (b) the studio's own ¥-cheap **drop-in promo posts that merely
  cross-reference** the workshop (事前のお申込み不要 / pay-at-door, no audition band).
  Also cut the 【学校情報】 school-profile blurb before genre-matching — it lists the
  *school's* curriculum ("クラシックバレエとコンテンポラリーダンス") and would leak a
  contemporary genre the workshop doesn't teach. Day tokens carry weekday markers
  with their own 月/日 ("5日（火）"), so anchor dates on year+month then read N日（曜）
  tokens, don't negate-class on 月 (see `studio_architanz`). A provider whose
  *main* site is an **agency/association** doing only 登録サポート (registration
  support) for *foreign* schools' auditions/summer schools (Paris Opéra, Cannes,
  CNSMD Lyon …) can still run **its own** dated student workshop on a **sister
  microsite** — scrape that, ignore the agency-mediated listings (those are other
  schools' programs, not this org's intensive). The own-workshop year is usually
  explicit in the title (no stamp inference), and a hyphen-joined day run
  "25日-26日-27日" needs a `(?:\d+日[-、…]*)+` capture (a non-greedy `[\d-]+日` stops at
  the first 日); see `temps_lie_ballet_workshop_japan`.
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
- [ ] Architecture / infra / ops / data-model / legal change? Mirror it in the internal doc-set (private companion `docs/`) + regenerate its `viewer.html` (see top)
- [ ] Branch → push → PR
