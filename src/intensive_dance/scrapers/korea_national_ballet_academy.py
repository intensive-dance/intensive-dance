"""국립발레단 부설 발레아카데미 (Korea National Ballet Academy), Seoul (KR).

API FIRST: none. The Korean National Ballet (KNB) site (a custom PHP CMS, no
public JSON API) server-renders the academy's "강좌 및 등록안내" (courses &
registration) page — the full text, including the year's term/vacation timetable,
is in the static HTML. The vacation-intensive dates live in a popup `<table>`
(titled "2026년도 성인취미반 수강료 납부기간 및 수강기간" — the adult hobby-class
tuition-payment and attendance schedule) that is present in the markup, so a
single plain fetch is enough; no JS render.

TLS NOTE: the host serves an incomplete certificate chain, so the shared client
can't validate it; we fetch with our own `verify=False` client (read-only public
page — see `fetch.make_client`), the same call the Princess Grace / Frankfurt
scrapers make. The EN subpages return HTTP 500 (not 404), so we read the Korean
(`/ko/`) page.

DISCOVERY: the academy runs two dated **vacation intensives** ("방학 특강", taught
by current KNB dancers / ballet stars, certificate for all participants) on the
published timetable — a 1-week 여름방학 (summer) and a 4-week 겨울방학 (winter, which
crosses the year boundary). They are separate dated editions with their own spans,
so we emit **one Offering per edition** (folding would lose the distinct dates).
The timetable's quarterly (분기) rows are the regular term, not intensives, and are
skipped — discovery keeps only the two 방학 (vacation) rows.

The dates live in a popup `<table>` titled "2026년도 성인취미반 수강료 납부기간 및
수강기간" (adult hobby-class tuition-payment and attendance schedule), not a
shared student table. We read it structurally by row (label cell → span cell).

KOREAN SOURCE: parsed language-agnostically. The span is `YYYY년 M월 D일(요일) ~
[YYYY년] M월 D일(요일) (N주)` — the start always carries the year; the end repeats it
only when the edition crosses into the next year (winter → 2027), so we inherit the
start's year when the end omits it. The `(N주)` week count is kept verbatim in the
schedule note. Source free text (titles, venue, registration note) is kept
faithfully in Korean, never translated inline.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-06):
  - Two Offerings from one page (per-edition split), distinct date spans.
  - A cross-year span (winter: 2026-12-14 → 2027-01-10) where the end states its
    own year, vs. a same-year span (summer) where it doesn't.
  - `make_client(verify=False)` for a broken TLS chain (no proxy needed — a plain
    direct fetch returns the real markup).
  - Faithful-minimal record: the vacation specials are first-come (선착순, no
    audition), with no per-edition fee or age restated, so prices / ageRange stay
    empty and `application.notes` keeps the 선착순 registration text — null/empty
    rather than borrowing the regular term's numbers.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import make_client
from intensive_dance.models import (
    Application,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.korean-national-ballet.kr"
PAGE = f"{BASE}/ko/academy/lecture"

ORG = Organization(
    name="국립발레단 부설 발레아카데미",
    slug="korea-national-ballet-academy",
    country="KR",
    city="Seoul",
)

# Venue + registration text kept faithfully in Korean (Seoul Arts Center).
VENUE_KO = "예술의전당 N studio"
# The vacation specials are first-come (no audition), unlike the audition-gated
# regular student term — kept verbatim as the application note.
REGISTER_NOTE_KO = "선착순 모집 (재수강생 우선 등록 후 신규생 접수)"


def scrape(client: httpx.Client) -> list[Offering]:  # noqa: ARG001 — see TLS NOTE
    # The shared client can't validate the incomplete cert chain; use our own.
    own = make_client(verify=False)
    try:
        resp = own.get(PAGE)
        resp.raise_for_status()
        html = resp.text
    finally:
        own.close()
    return _build_offerings(html)


# A vacation-row label → the slug key and faithful Korean title word.
class _Edition:
    def __init__(self, label_ko: str, key: str, timezone: str) -> None:
        self.label_ko = label_ko  # the timetable row label we match on
        self.key = key  # the offering-slug stem
        self.timezone = timezone


_EDITIONS = [
    _Edition("여름방학", "summer", "Asia/Seoul"),
    _Edition("겨울방학", "winter", "Asia/Seoul"),
]


def _build_offerings(html: str) -> list[Offering]:
    rows = _period_rows(html)
    offerings: list[Offering] = []
    for edition in _EDITIONS:
        span = rows.get(edition.label_ko)
        if span is None:
            continue
        start, end = _date_span(span)
        if start is None and end is None:
            continue
        offerings.append(_build_offering(edition, span, start, end))
    return offerings


def _build_offering(
    edition: _Edition,
    span: str,
    start: date | None,
    end: date | None,
) -> Offering:
    anchor = start or end
    assert anchor is not None  # guarded in _build_offerings
    season = str(anchor.year)
    return Offering(
        id=f"korea-national-ballet-academy/{edition.key}-intensive-{season}",
        source=Source(provider="korea-national-ballet-academy", url=PAGE, scrapedAt=now_utc()),
        title=f"국립발레단 발레아카데미 {edition.label_ko} 특강 {season}",
        # The vacation specials don't enumerate their own curriculum, so we record
        # only the unambiguous `classical` (it's a ballet academy intensive) and
        # don't leak pointe/repertoire from the regular term that doesn't apply.
        genres=["classical"],
        organization=ORG,
        location=Location(venue=VENUE_KO, city="Seoul", country="KR"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone=edition.timezone,
            notes=parse.clean(span),
        ),
        application=Application(notes=REGISTER_NOTE_KO),
    )


# --- timetable rows -----------------------------------------------------------
#
# The year's term/vacation schedule is a popup <table> whose first column is the
# row label (분기 / 여름방학 / 겨울방학) and whose second column is the date span. We
# read it structurally by row (label cell → span cell), so the quarterly rows and
# the empty 수강기간 column never confuse the match.


def _period_rows(html: str) -> dict[str, str]:
    tree = HTMLParser(html)
    rows: dict[str, str] = {}
    for tr in tree.css("table tr"):
        cells = [parse.clean(td.text(separator=" ")) for td in tr.css("td")]
        if len(cells) < 2:
            continue
        label, span = cells[0], cells[1]
        if label in {"여름방학", "겨울방학"} and span:
            rows[label] = span
    return rows


# --- dates --------------------------------------------------------------------
#
# Span: "2026년 7월 27일(월) ~ 8월 3일(월) (1주)" — the start always carries the year;
# the end repeats it only when the edition crosses into the next year (winter →
# "... ~ 2027년 1월 10일(일) (4주)"), so the end inherits the start's year otherwise.

_START = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
# The end is the date AFTER the "~" separator; its year is optional.
_END = re.compile(r"[~∼〜～\-–]\s*(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일")


def _date_span(span: str) -> tuple[date | None, date | None]:
    start_m = _START.search(span)
    if not start_m:
        return None, None
    start_year, start_month, start_day = (int(g) for g in start_m.groups())
    start = date(start_year, start_month, start_day)

    end_m = _END.search(span, start_m.end())
    if not end_m:
        return start, None
    end_year = int(end_m.group(1)) if end_m.group(1) else start_year
    end = date(end_year, int(end_m.group(2)), int(end_m.group(3)))
    return start, end
