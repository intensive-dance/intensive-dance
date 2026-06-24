"""Elmhurst Ballet School — Summer School (Seniors + Juniors), Birmingham.

API FIRST
elmhurstballetschool.org is a custom PHP site (a `/turbine/css.php` preprocessor),
**not** WordPress — `/wp-json/` 404s — and carries no `Event`/`Course` `ld+json`
(only nav chrome). It also sits behind a StackProtect/Cloudflare challenge that
403s a plain datacenter fetch, so this routes through the fetch proxy's `auto=1`
tier (which clears the challenge and returns the server-rendered HTML — no JS
render needed). The courses page is one Bootstrap accordion; each programme is a
`#collapseN` panel whose `<h4>`/`<strong>` labels carry the dated detail.

DISCOVERY — one Offering per dated Summer School programme (the open courses only).
The courses accordion lists six panels; four are out of scope — two full-time
vocational tracks (Lower/Upper School), the year-round "Ballet and Beyond"
recreational programme, and the "Elmhurst Young Dancers" associate scheme — plus
the **Silver Swans Summer Retreat**, a recreational 55+ adult retreat (not a
student intensive). That leaves the **Summer School** panel, which holds two dated
2026 student editions, emitted as one Offering each:
  - **Seniors (ages 14–18)** — bookable as Week 1 (10–15 Aug), Week 2 (17–22 Aug),
    or a two-week course (10–22 Aug). Modelled as one Offering spanning the
    two-week option with a `Session` per week (each week runs a different
    repertoire) and all four fees (1-/2-week × residential/non-residential).
  - **Juniors (ages 10–13)** — a single 3-day edition (25–27 Aug).
Year-stamped slugs because the source labels the edition by year.

The courses page states only "Applications are now closed, however please contact
us …" — no audition/photo brief of its own (the site's Photograph/Video
Requirements pages belong to the *full-time* audition flow, not the Summer
School), so `application.status = "closed"` with that note and `requirements = []`
(not stated here) rather than inventing a photo gate.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-12)
- Proxy `auto=1` tier to clear a Cloudflare/StackProtect challenge on a non-WP,
  no-ld+json custom site. The gate clears non-deterministically and intermittently
  surfaces a transient 401 (formerly 403) through the proxy; `fetch._RETRY_STATUS`
  re-sends those, so a single blip no longer fails the scraper (issues #347/#351/
  #359/#364).
- Accordion-panel slicing by `<h4>` sub-headings into two programmes.
- English ordinal day span ("Monday 10th – Saturday 15th August 2026") with the
  month/year stated once for both days; arrival lines (no year) ignored.
- Multi-session Offering: Seniors → `Session` per week + two-week overall span.
- Residential/non-residential fee matrix → `Price` list (GBP); residential adds
  `accommodation`, all include `tuition`+`meals` ("all food and drink"); the
  "£50 non-refundable deposit" line is not a price.
- Genres scoped per programme's own curriculum (Seniors adds pointe; Juniors does
  not), not the shared intro.
- `application.status = "closed"` from the panel's own text.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import PROXY_PARAMS_HEADER
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    PriceInclude,
    Schedule,
    Session,
    Source,
    now_utc,
)

PAGE = "https://elmhurstballetschool.org/en/dance/courses/"
SLUG = "elmhurst-ballet-school"
PANEL = "#collapse6"  # the "Summer School" accordion panel

ORG = Organization(name="Elmhurst Ballet School", slug=SLUG, country="GB", city="Birmingham")

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "classical")),
    ("repertoire", ("repertoire",)),
    ("pointe", ("pointe",)),
    ("contemporary", ("contemporary",)),
]

# "Monday 10th – Saturday 15th August 2026" — day, optional weekday before day 2,
# month + year stated once. Arrival lines carry no year, so they don't match.
_SPAN = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*[–—-]\s*(?:[A-Za-z]+\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+("
    + parse.MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)
_AGES = re.compile(r"ages?\s+(\d{1,2})\s*[–—-]\s*(\d{1,2})", re.IGNORECASE)
_PRICE_LINE = re.compile(r"(non-residential|residential)\s*:?\s*£\s*([\d.,]+)", re.IGNORECASE)
_DURATION = re.compile(r"^\s*(one week|two weeks)\b", re.IGNORECASE)


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE, headers={PROXY_PARAMS_HEADER: "auto=1"})
    resp.raise_for_status()
    return _build_offerings(resp.text)


def _panel_segments(html: str) -> dict[str, str]:
    """The Summer-School panel sliced into per-programme text by its `<h4>`s."""
    tree = HTMLParser(html)
    panel = tree.css_first(PANEL)
    if panel is None:
        return {}
    # Normalize nbsp (the live `<h4>`s use one) but keep newlines so the per-line
    # date/fee parsing below still works.
    text = panel.text(separator="\n").replace("\xa0", " ")
    heads = [h.text().replace("\xa0", " ").strip() for h in panel.css("h4")]
    heads = [h for h in heads if h]
    segments: dict[str, str] = {}
    for i, head in enumerate(heads):
        start = text.find(head)
        if start < 0:
            continue
        nxt = text.find(heads[i + 1]) if i + 1 < len(heads) else len(text)
        segments[head] = text[start : nxt if nxt > start else len(text)]
    return segments


def _age_range(heading: str) -> dict | None:
    m = _AGES.search(heading)
    return {"min": int(m.group(1)), "max": int(m.group(2))} if m else None


def _span(line: str) -> tuple[date, date] | None:
    m = _SPAN.search(line)
    if not m:
        return None
    d1, d2, month_name, year = m.groups()
    month = parse.MONTHS[month_name.lower()]
    return date(int(year), month, int(d1)), date(int(year), month, int(d2))


def _dates(segment: str) -> tuple[date | None, date | None, list[Session], str | None]:
    """Overall span + a Session per labelled week (Seniors) from the dates block."""
    weeks: list[Session] = []
    two_week: tuple[date, date] | None = None
    single: tuple[date, date] | None = None
    raw: list[str] = []
    for line in segment.splitlines():
        line = parse.clean(line)
        span = _span(line)
        if not span:
            continue
        raw.append(line)
        low = line.lower()
        if low.startswith("week "):
            weeks.append(Session(label=line.split(":")[0].strip(), start=span[0], end=span[1]))
        elif "two-week" in low or "two week" in low:
            two_week = span
        else:
            single = single or span

    if weeks:
        overall = two_week or (
            min(s.start for s in weeks if s.start),
            max(s.end for s in weeks if s.end),
        )
        return overall[0], overall[1], weeks, " | ".join(raw) or None
    if single:
        return single[0], single[1], [], " | ".join(raw) or None
    return None, None, [], " | ".join(raw) or None


def _prices(segment: str) -> list[Price]:
    prices: list[Price] = []
    duration: str | None = None
    for line in segment.splitlines():
        line = parse.clean(line)
        if dur := _DURATION.match(line):
            if not _PRICE_LINE.search(line):
                duration = dur.group(1).title()
                continue
        m = _PRICE_LINE.search(line)
        if not m:
            continue
        amount = parse.parse_amount(m.group(2))
        if amount is None:
            continue
        residential = m.group(1).lower() == "residential"
        kind = "Residential" if residential else "Non-residential"
        label = f"{duration} — {kind}" if duration else kind
        includes: list[PriceInclude] = ["tuition", "meals"]
        if residential:
            includes.append("accommodation")
        prices.append(Price(amount=amount, currency="GBP", label=label, includes=includes))
    return prices


def _application_note(html: str) -> str | None:
    panel = HTMLParser(html).css_first(PANEL)
    if panel is None:
        return None
    for line in panel.text(separator="\n").splitlines():
        line = parse.clean(line)
        if line.lower().startswith("applications are now closed"):
            return line
    return None


def _build_offerings(html: str) -> list[Offering]:
    segments = _panel_segments(html)
    note = _application_note(html)
    offerings: list[Offering] = []
    for heading, segment in segments.items():
        start, end, sessions, dates_note = _dates(segment)
        year = start.year if start else None
        slug = "senior" if "senior" in heading.lower() else "junior"
        title = f"Summer School ({'Seniors' if slug == 'senior' else 'Juniors'})"
        offerings.append(
            Offering(
                id=f"{SLUG}/{slug}-summer-school-{year}"
                if year
                else f"{SLUG}/{slug}-summer-school",
                source=Source(provider=SLUG, url=PAGE, scrapedAt=now_utc()),
                title=f"{title} {year}" if year else title,
                genres=parse.match_genres(segment, _GENRE_KEYWORDS, default=["classical"]),
                ageRange=_age_range(heading),
                organization=ORG,
                location=Location(venue="Elmhurst Ballet School", city="Birmingham", country="GB"),
                schedule=Schedule(
                    season=str(year) if year else "unknown",
                    start=start,
                    end=end,
                    timezone="Europe/London",
                    sessions=sessions,
                    notes=dates_note,
                ),
                prices=_prices(segment),
                application=Application(
                    status="closed" if note else None,
                    url=PAGE,
                    notes=note,
                ),
            )
        )
    return offerings
