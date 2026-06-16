# Data-review pattern catalog

The failure modes a review pass looks for, newest learnings appended at the
bottom. Each entry: **what goes wrong**, **how to spot it in the store**, **how
to confirm against the source**, **the fix**. When a review turns up an issue
whose shape isn't already here, append a new entry (see "Extending this catalog"
in `SKILL.md`) — that is how the skill gets sharper over time.

Field keys below match the review UI / issue body (`application.requirements`,
`schedule.sessions`, …). The data shape is `docs/data-model.md`.

---

## P1 — Wrong audition attributed to the offering (two flows on one page)

- **Wrong:** `application.requirements` (or `application.notes`) describes an
  audition that belongs to a *different* programme than the offering — most
  often a school's year-round **season/company audition** bleeding into a
  **summer-intensive** record, or vice versa.
- **Spot it:** the requirements text mentions a season/year that isn't the
  offering's (`"season 2026-2027"` on a summer-2026 course), age bands that
  don't match `ageRange`, or wording like "for entry to the Academy" on a short
  course. A bare `notes` blob with no structured `requirements` entries is a
  smell that the scraper grabbed the first audition paragraph it saw.
- **Confirm:** read the source page section-by-section (often the real summer
  requirements are *further down* the page than the season-audition teaser); or
  ground it — "Does <provider>'s <year> summer intensive itself serve as the
  audition, and what must applicants submit (CV / photo / video)?"
- **Fix:** attribute only the offering's own audition. Encode the hard facts as
  structured `requirements` (`cv`, `photos`/`video` with specificity, etc.) and
  keep a short human summary + a link to the full source requirements in
  `notes` — do **not** dump the page's full audition prose. (Origin: #258,
  Académie Princesse Grace — the summer intensive doubles as the season
  audition, but the page's detailed requirements sit below the teaser.)

## P2 — Invented `application.status`

- **Wrong:** `application.status` set to `open`/`closed` when the source never
  states it. "Be faithful, fail open" — `null` means not stated.
- **Spot it:** a status present with no supporting `deadline`/`opensAt` and no
  "applications open/closed" phrasing in `notes`; many providers in one batch
  all defaulting to `open`.
- **Confirm:** check the source for an explicit open/closed statement.
- **Fix:** drop the field (leave it unset). Same goes for guessed `deadline`.
  (Origin: ballettratten / europaballett hardcoded `status="open"`.)

## P3 — Genre leakage from prose, not curriculum

- **Wrong:** `genres` lists a style the programme doesn't actually teach,
  picked up from a blurb ("contemporary works", a school-profile paragraph) or
  an out-of-scope sibling class.
- **Spot it:** a genre with no matching class/heading in the curriculum; a
  `contemporary`/`character` tag on an otherwise pure-classical short course.
- **Confirm:** match genres against the syllabus headings, not the marketing
  description; ground "What classes/styles are on the <provider> <year>
  intensive timetable?"
- **Fix:** scope genre keyword matching to the curriculum list; cut
  school-profile blurbs before matching.

## P4 — Folded multi-session / multi-track offering

- **Wrong:** one `Offering` spans what are really several distinct courses
  (per week, per track, per city, per age cohort) — losing distinct
  dates/ages/fees, or fabricating one giant date span.
- **Spot it:** a `schedule.start→end` far longer than a normal intensive; an
  `ageRange` that's suspiciously wide; `notes` listing several blocks.
- **Confirm:** does the source sell these as separate bookings? Parallel dated
  sessions → one Offering per session (or a `Session` each when they differ only
  by age/gender).
- **Fix:** split into one Offering per place/track, or add `schedule.sessions`.

## P5 — Stale / mis-picked dates

- **Wrong:** `schedule.start`/`end` carries a prior edition's dates, a
  deadline date mistaken for the start, or a wrong year.
- **Spot it:** dates in the past relative to the season; `start` equal to a
  known registration deadline; a year that doesn't match `title`/`season`.
  (Note: genuinely *ended* cycles are kept on purpose — IDR-24. Past dates are
  only a bug when they contradict the title's year, not merely because they're
  past.)
- **Confirm:** ground/read the source for the current edition's dates; watch
  for year-less date lines (year comes from the title) and full-width digits on
  JP pages.
- **Fix:** re-parse from the current-edition block; keep raw text in
  `schedule.notes`.

## P6 — Price missing currency / `includes`, or wrong amount

- **Wrong:** a `Price` with the wrong `currency` (defaulted, not the local
  one), missing `includes`, or tuition conflated with room & board.
- **Spot it:** currency that doesn't match the venue country; a single price
  where the source quotes tuition + accommodation separately; **only a small
  application fee captured** while the real tuition tier (in a sibling "Course
  fees" section/column the parser skipped) is missing.
- **Confirm:** the source's fee table — check for a *second* fee block.
- **Fix:** one `Price` per quoted line, local `currency`, correct `includes`;
  concatenate sibling fee sections before parsing. (Origin: #170 — RBS captured
  the £48 application fee but not the £865/£1485 tuition in a parallel section.)

## P7 — Empty / placeholder offering that shouldn't exist

- **Wrong:** an Offering with no genres / no dates / bare registration form —
  a genre-less stub, or a programme whose own page carries no structured detail.
- **Spot it:** empty `genres`, null dates, generic `title`.
- **Confirm:** does the source page actually carry this edition's own detail,
  or is it a contact-us / "no items found" template?
- **Fix:** drop it (don't emit empty-genre Offerings); build only editions with
  real per-edition detail.

## P8 — Currency guessed from an ambiguous symbol, not the venue country

- **Wrong:** a bare `$`/`¥`/`£` resolved to a hardcoded default (USD/CNY) when
  the course runs in a country that uses that glyph for a *different* currency
  (AUD/SGD/JPY/…).
- **Spot it:** `prices[].currency` doesn't match `location.country` — e.g. an
  `AU` venue priced in `USD`, a Singapore course in `USD`. Greppable: scan each
  `data/*.json` for currency/country mismatches.
- **Confirm:** the source fee text; ground "what currency are <provider>'s
  <city> fees quoted in?".
- **Fix:** map the bare symbol against the offering's resolved country
  (`$`→AUD for AU, SGD for SG, … default USD). (Origin: 898074c
  russian-masters-ballet, ee87058 royal-ballet-school — country-aware glyphs.)

## P9 — Application deadline lands *after* the course runs

- **Wrong:** a year-less deadline ("December 22") stamped with the program's
  year, producing a deadline later than the intensive it gates — typically a
  winter camp whose application closes the *prior* December.
- **Spot it:** `application.deadline` > `schedule.end` (or after `start`). A
  crisp, greppable invariant: a deadline should never be after the course ends.
- **Confirm:** the source's application/registration line and the course dates.
- **Fix:** when the deadline month falls later in the year than the course
  month, roll the deadline year back one. (Origin: fc1c7e6
  ballet-workshops-bucharest `_deadline_rollback` — Dec-2025 deadline for a
  Jan-2026 camp.)

## P10 — Long-term / vocational program emitted as an intensive (scope)

- **Wrong:** a year-round *Ausbildung* / propedeutica / multi-month training
  track scraped as if it were a short intensive — a scope violation ("stub,
  don't fake"), not just a date error.
- **Spot it:** a `schedule` span far longer than an intensive (≳ 60 days, or an
  autumn→spring span); a `title` like "preparatory" / "propedeutico" /
  "full-time".
- **Confirm:** is the source selling a dated short course, or year-round
  vocational training? (Many vocational schools *also* sell a public summer
  school — build that, not the full-time track.)
- **Fix:** drop the long-term offering; keep only the public short course.
  (Origin: #187 — RBS `_is_long_term` >60-day guard; Scala removed
  `_build_propedeutica`.) See AGENTS.md scope rules.

## P11 — Same-month date range collapsed to a single day

- **Wrong:** a same-month span ("3–7 April", "19 and 20 February") parsed by a
  `DD Month` regex that only catches the *trailing* day, so `start` == `end`.
- **Spot it:** `schedule.start` equals `schedule.end` while `schedule.notes` /
  title imply a multi-day course. Greppable across the store.
- **Confirm:** the source's date line.
- **Fix:** match the leading day too (`DD[–/ and ]DD Month`). (Origin: #135
  royal-ballet-school.)

## P12 — Silent truncation: fewer offerings than the source lists

- **Wrong:** the scraper drops a subset of real editions — distinct from the
  zero-offering structural audit, which only catches a *total* miss. Causes
  seen: an un-paginated API (`per_page` cap, ignoring `X-WP-TotalPages`); a URL
  sanitizer that mangles absolute/protocol-relative links (`//host` → `/host`)
  so some detail pages are never followed.
- **Spot it:** the store has noticeably fewer offerings than the source index;
  a known city/track/course is absent. (Compare count to the live listing.)
- **Confirm:** count editions on the source index vs. the store.
- **Fix:** paginate via `X-WP-TotalPages` (use `wp.fetch_all`/`fetch_children`);
  parse URLs with `urllib.parse.urlsplit`, not string slicing. (Origin: ee87058
  wp pagination, 898074c russian-masters-ballet `urlsplit`.)

## P13 — Archived / past-listing rows scraped as live offerings

- **Wrong:** a "Past guests" / "previous editions" archive block (footer
  carousel, news clippings) parsed as upcoming offerings because it carries
  dates and names. **Note:** this is *not* the IDR-24 rule — a genuinely-run
  edition is kept on purpose. The bug is emitting rows from an *archive* section
  that were never bookable editions of their own.
- **Spot it:** offerings whose only source is a past-events/old-year carousel,
  with no registration of their own; clusters of stale-year stubs.
- **Confirm:** does the source list these as their own editions, or as a
  retrospective of past guests?
- **Fix:** restrict parsing to the upcoming/current segment of the page.
  (Origin: fc1c7e6 ballet-workshops-bucharest `_upcoming_segment`.)

## P14 — Empty `genres` on a single-discipline institution (under-match)

- **Wrong:** an Offering from a school that teaches one discipline (e.g. a
  *ballet* school) ships `genres: []` because its keyword matcher found no style
  word in a **sparse page** (a thin masterclass/announcement page that lists
  dates/venue but never says "classical"/"ballet"). The inverse of P3's *over*-
  match: here the matcher *under*-matches and emits a genre-less Offering (which
  the "don't emit empty-genre Offerings" rule says shouldn't exist).
- **Spot it:** `genres == []` on a provider whose other offerings are all
  classical (greppable across `data/<slug>.json`); a known ballet school with a
  genre-less row. Distinguish from P7 (a genuine non-offering): here the row IS a
  real dated edition, just thinly described.
- **Confirm:** is the provider single-discipline (its whole catalogue is ballet)?
  Does the sparse page describe a real edition (dates/venue) vs a placeholder?
- **Fix:** give the discipline matcher a `default=[...]` (e.g. `["classical"]`)
  so a no-keyword page falls back to the institution's base discipline rather
  than emitting empty genres — only when the provider genuinely teaches nothing
  else. Don't default a multi-discipline provider. (Origin: royal-ballet-school
  Livorno/Spain masterclasses — sparse pages, `_genres` had no default.)
