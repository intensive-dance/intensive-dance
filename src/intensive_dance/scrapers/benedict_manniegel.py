"""Benedict Manniegel Ballet School & Academy (Munich, DE) — its Osterworkshop.

API FIRST: WordPress REST is live (`/wp-json/`, 200) with clean `content.rendered`
on the "Workshops und Events" page — but that page is **evergreen**: it describes
the recurring Easter (Oster-) and Summer workshops conceptually, with no dated
edition (registration "erfolgt online über das jeweilige Formular auf dieser
Seite"). The actual dated editions are published only as **Stundenplan (timetable)
PDFs in the WP media library** (`/wp-json/wp/v2/media`). So this is a PDF scrape
(pypdf) of the current Osterworkshop schedule, discovered through the media API —
no proxy needed (the host serves both the API and the PDFs directly).

Only the **Osterworkshop** schedule PDF is structured enough to scrape
deterministically: its legend carries the per-level age bands, the genres (class
names) and the faculty. The SummerWorkshop Stundenplan uses a different day-header
format and carries **no** age-band legend (summer ages live only on year-specific
marketing flyers that aren't published for the current year), so it is
intentionally out of scope here.

DISCOVERY: one dated edition → **one Offering**. The media library keeps every
past revision/edition (`Stdplan_Osterworkshop_2025_003`, `…_2026_004`, …); a
superseded revision is an internal artifact, not a separately-listed edition, so
we select the **latest year, latest revision** `Stdplan_Osterworkshop_<year>_<rev>`
PDF — the current edition the school promotes. This rolls forward automatically
(2027 supersedes 2026); it is *discovery* (pick the live edition), not a date cut.

The school's full-time, multi-year Ausbildung is out of scope; the Osterworkshop
is a public, open-enrollment, dated short course (online-form registration, no
audition) — exactly in scope.

LANGUAGE NOTE: the PDFs are German. Parsed language-agnostically where possible —
numeric day.month tokens from the day-header row + the year from the media slug
give the dates; numeric "N-M J." / "ab N J." bands give the ages; genres key off
the German class names. Faculty names come verbatim from the LEHRKRÄFTE legend.
The emitted title is built from the slug, not the (letter-spaced) PDF text.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-12):
  - Media-library discovery: pick latest `Stdplan_Osterworkshop_<year>_<rev>`.
  - PDF scrape (pypdf) of a timetable; dates from "DD.MM." day headers + slug year
    (Osterworkshop 2026 → 7–11 April 2026).
  - Open-topped ageRange {min: 5} (PreBallet 5–7 … Level IV "Ab 16 J." has no cap).
  - GENRES off the class names: classical (Klassisches Ballett) + pointe (Spitze)
    + character (Charaktertanz); Tanzgeschichte/Dance History is not a genre.
  - Levels beginner/intermediate/advanced across the PreBallet→Level IV bands.
  - Faculty from the LEHRKRÄFTE legend (initials + full name).
  - Open registration, no audition → requirements [NoneReq]; prices [] (the
    schedule PDF states none); deadline None (not stated).
"""

from __future__ import annotations

import io
import re
from datetime import date

import httpx
from pypdf import PdfReader

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    NoneReq,
    Offering,
    Organization,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://www.benedictmanniegel.de"
INFO_URL = f"{BASE}/academy/workshops-events/"
SLUG = "benedict-manniegel"

ORG = Organization(
    name="Benedict Manniegel Ballet School & Academy",
    slug=SLUG,
    country="DE",
    city="Munich",
)
VENUE = "Benedict Manniegel Ballet School & Academy"

# Media titles look like "Stdplan_Osterworkshop_2026_004" (year, then revision).
_SCHEDULE_TITLE = re.compile(r"Stdplan[_ ]Osterworkshop[_ ](\d{4})[_ ](\d+)", re.IGNORECASE)


def scrape(client: httpx.Client) -> list[Offering]:
    media = wp.fetch_all(
        client,
        "media",
        base=BASE,
        params={"search": "Osterworkshop", "_fields": "title,source_url"},
    )
    chosen = _select_schedule(media)
    if chosen is None:
        return []
    url, year = chosen
    resp = client.get(url)
    resp.raise_for_status()
    return _build_offerings(_pdf_text(resp.content), year, INFO_URL)


def _select_schedule(media: list[dict]) -> tuple[str, int] | None:
    """The latest-year, latest-revision Osterworkshop timetable PDF in the library."""
    best: tuple[int, int, str] | None = None  # (year, revision, url)
    for item in media:
        title = (item.get("title") or {}).get("rendered", "")
        url = item.get("source_url", "")
        m = _SCHEDULE_TITLE.search(title)
        if not m or not url.lower().endswith(".pdf"):
            continue
        year, rev = int(m.group(1)), int(m.group(2))
        if best is None or (year, rev) > (best[0], best[1]):
            best = (year, rev, url)
    return (best[2], best[0]) if best else None


def _pdf_text(data: bytes) -> str:
    """Raw timetable text, newlines preserved (the legend parses line-by-line)."""
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def _build_offerings(text: str, year: int, info_url: str) -> list[Offering]:
    start, end = _date_range(text, year)
    if start is None:
        return []  # no parseable day-header row → nothing to emit

    season = str(year)
    return [
        Offering(
            id=f"{SLUG}/osterworkshop-{season}",
            source=Source(provider=SLUG, url=info_url, scrapedAt=now_utc()),
            title=f"Osterworkshop {season}",
            genres=_genres(text),
            level=_levels(text),
            ageRange=_age_range(text),
            organization=ORG,
            location=Location(venue=VENUE, city="Munich", country="DE"),
            schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Berlin"),
            teachers=_teachers(text),
            prices=[],  # the schedule PDF states no fees
            application=Application(
                deadline=None,
                url=info_url,
                # Open-enrollment short course — registration via an online form,
                # no audition/photos/video/CV asked of the dancer → explicitly
                # NoneReq, not unknown ([]).
                requirements=[NoneReq()],
            ),
        )
    ]


# --- dates: "DD.MM." tokens from the day-header row + the slug year ------------
#
# The header row reads "DIENSTAG 07.04. MITTWOCH 08.04. … SAMSTAG 11.04."; the
# year is not in the timetable, so it comes from the media slug. Times use ":"
# (no false matches) and "1. OG" / "24. März" lack a trailing dotted number.

_DAY = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.")


def _date_range(text: str, year: int) -> tuple[date | None, date | None]:
    days: list[date] = []
    for d, mon in _DAY.findall(text):
        d, mon = int(d), int(mon)
        if 1 <= mon <= 12 and 1 <= d <= 31:
            days.append(date(year, mon, d))
    if not days:
        return None, None
    return min(days), max(days)


# --- ages: per-level bands "N-M J." plus an open-topped "ab N J." --------------
#
# 2026: PreBallet 5-7 / Level I 8-10 / II 10-12 / III 13-15 / IV "Ab 16 J."
# (no cap). The open band leaves the overall max null; "ab ca. N" also occurs.

_BAND = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*J\.")
_OPEN = re.compile(r"\b[Aa]b\s+(?:ca\.\s*)?(\d{1,2})\s*J\.")


def _age_range(text: str) -> dict | None:
    bands = [(int(a), int(b)) for a, b in _BAND.findall(text) if 3 <= int(a) <= int(b) <= 30]
    opens = [int(m.group(1)) for m in _OPEN.finditer(text) if 3 <= int(m.group(1)) <= 30]
    if not bands and not opens:
        return None
    lows = [a for a, _ in bands] + opens
    if opens:  # an open-ended top band → null max
        return {"min": min(lows)}
    return {"min": min(lows), "max": max(b for _, b in bands)}


# --- levels: PreBallet/taster → Level IV (vocational level) --------------------

_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("preballet", "schnupper", "basis", "anfänger")),
    ("intermediate", ("level ii", "level iii", "mittelstufe")),
    ("advanced", ("level iv", "fortgeschritten", "ausbildung")),
]


def _levels(text: str) -> list[Level]:
    return parse.match_genres(text, _LEVEL_KEYWORDS, default=[])


# --- genres: keyed off the class names, not loose prose -----------------------
#
# Klassisches Ballett, Spitze, Charaktertanz are register genres;
# Tanzgeschichte / Dance History is not.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("klassisch", "ballett")),
    ("pointe", ("spitze",)),
    ("character", ("charakter",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- faculty: the LEHRKRÄFTE legend ("<initials> <Full Name>" per line) -------

_FACULTY_LINE = re.compile(
    r"^[A-ZÄÖÜ][A-Za-zÄÖÜ]{0,3}\s+"
    r"([A-ZÄÖÜ][a-zäöüß]+(?:[-\s][A-ZÄÖÜ][a-zäöüß]+)+)\s*$"
)


def _teachers(text: str) -> list[Teacher]:
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if "LEHRKRÄFTE" in ln.upper())
    except StopIteration:
        return []

    names: list[str] = []
    for ln in lines[start + 1 :]:
        ln = ln.strip()
        if not ln or ln.lower().startswith("stand"):
            break
        m = _FACULTY_LINE.match(ln)
        if m:
            names.append(parse.clean(m.group(1)))
    return [Teacher(name=n) for n in names]
