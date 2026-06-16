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
  where the source quotes tuition + accommodation separately.
- **Confirm:** the source's fee table.
- **Fix:** one `Price` per quoted line, local `currency`, correct `includes`.

## P7 — Empty / placeholder offering that shouldn't exist

- **Wrong:** an Offering with no genres / no dates / bare registration form —
  a genre-less stub, or a programme whose own page carries no structured detail.
- **Spot it:** empty `genres`, null dates, generic `title`.
- **Confirm:** does the source page actually carry this edition's own detail,
  or is it a contact-us / "no items found" template?
- **Fix:** drop it (don't emit empty-genre Offerings); build only editions with
  real per-edition detail.
