"""abcDance — Academy of Ballet & Contemporary Dance, Wiener Neustadt (+ Trumau), AT.

API FIRST: none. The site runs on **Jimdo Creator** (no `/wp-json/` — it 403s —,
no `ld+json`, no state blob), so this is a plain HTML text scrape via `selectolax`.

DISCOVERY: the Sommer 2026 hub (`/sommer-2026/`) and its `programm`/`stundenplan`
sub-pages render their detailed week-by-week programme **only as images**
(alt-less `image.jimcdn.com/.../image.png`) — NOT machine-readable, so we never
OCR them. The one place the camp dates live as **real text** is the Tanz-Camp
registration form (`/sommer-2026/anmeldung-sommer-tanzcamp-2026/`): each camp is a
checkbox whose `value`/label reads "CAMP 1 (20.-24. Juli 2026; 5-15 Jahre)". Those
checkbox labels are the source of truth for the dated editions. The three camps
are distinct dated runs (two in July, one Aug→Sep), so we emit **one Offering per
camp** (faithful to the data-model's one-Offering-per-dated-edition rule).

The registration deadline ("Anmeldungsdeadline: 4. Juli 2026") is stated as text
on the `programm-sommer-2026` page (anchored on that label — a loose date regex
would mis-match the "24. Juli" inside a camp span), so we fetch that page too.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-12): per-edition Offerings off
one form; same-month *and* cross-month German date ranges ("30. August-5.
September 2026"); shared age band (5-15); a stated deadline from a second page;
`NoneReq` (the form asks only for name/DOB/prior dance experience — no audition
material). Genres are **not** stated per camp in text (the org name lists
ballet+contemporary, but that's the academy's full curriculum, not the camp's), so
we fall back to the ballet-register default `["classical"]` rather than leak
`contemporary` from the menu. No prices in text (they live on an image page).
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Location,
    NoneReq,
    Offering,
    Organization,
    Schedule,
    Source,
    now_utc,
)

BASE = "https://www.abcdance.at"
CAMP_FORM = f"{BASE}/sommer-2026/anmeldung-sommer-tanzcamp-2026/"
PROGRAMM = f"{BASE}/sommer-2026/programm-sommer-2026/"

ORG = Organization(
    name="abcDance — Academy of Ballet & Contemporary Dance",
    slug="abc-dance",
    country="AT",
    city="Wiener Neustadt",
)

_MONTHS = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}
_MONTHALT = parse.months_alt(_MONTHS)

# A camp checkbox label, e.g. "CAMP 1 (20.-24. Juli 2026; 5-15 Jahre)" — number,
# date span, then the age band. The span is parsed separately (two shapes below).
_CAMP = re.compile(
    r"CAMP\s+(\d+)\s*\((.+?);\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s*Jahre\)",
    re.IGNORECASE,
)
# Same month: "20.-24. Juli 2026" (year + month stated once, after both days).
_RANGE_SAME = re.compile(
    r"(\d{1,2})\.\s*[-–]\s*(\d{1,2})\.\s*(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
# Cross month: "30. August-5. September 2026" (year stated once, at the end).
_RANGE_CROSS = re.compile(
    r"(\d{1,2})\.\s*(" + _MONTHALT + r")\s*[-–]\s*(\d{1,2})\.\s*(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)
# "Anmeldungsdeadline: 4. Juli 2026" — anchored on the label, never a loose date.
_DEADLINE = re.compile(
    r"Anmeldungsdeadline:\s*(\d{1,2})\.\s*(" + _MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def scrape(client: httpx.Client) -> list[Offering]:
    form = client.get(CAMP_FORM)
    form.raise_for_status()
    prog = client.get(PROGRAMM)
    prog_html = prog.text if prog.is_success else ""
    return _build_offerings(form.text, prog_html, date.today())


def _build_offerings(form_html: str, prog_html: str, today: date) -> list[Offering]:
    text = _text(form_html)
    deadline = _deadline(_text(prog_html))

    offerings: list[Offering] = []
    for num, span, age_lo, age_hi in _CAMP.findall(text):
        start, end = _date_span(span)
        if start is None or end is None:
            continue  # no machine-readable date → never fabricate
        offerings.append(_offering(int(num), span, start, end, int(age_lo), int(age_hi), deadline))
    return offerings


def _offering(
    num: int,
    span: str,
    start: date,
    end: date,
    age_lo: int,
    age_hi: int,
    deadline: date | None,
) -> Offering:
    season = str(start.year)
    return Offering(
        id=f"abc-dance/sommer-tanzcamp-{num}-{season}",
        source=Source(provider="abc-dance", url=CAMP_FORM, scrapedAt=now_utc()),
        title=f"Sommer-Tanzcamp {num} {season}",
        genres=["classical"],  # camp text states no genre; see docstring
        ageRange={"min": age_lo, "max": age_hi},
        organization=ORG,
        location=Location(city="Wiener Neustadt", country="AT"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Vienna",
            notes=parse.clean(span),
        ),
        application=Application(
            url=CAMP_FORM,
            deadline=deadline,
            # The form collects name/DOB/prior dance experience only — no audition material.
            requirements=[NoneReq()],
        ),
    )


def _text(html: str) -> str:
    if not html:
        return ""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _date_span(span: str) -> tuple[date | None, date | None]:
    m = _RANGE_CROSS.search(span)
    if m:
        d1, mon1, d2, mon2, year = m.groups()
        return (
            date(int(year), _MONTHS[mon1.lower()], int(d1)),
            date(int(year), _MONTHS[mon2.lower()], int(d2)),
        )
    m = _RANGE_SAME.search(span)
    if m:
        d1, d2, mon, year = m.groups()
        num = _MONTHS[mon.lower()]
        return date(int(year), num, int(d1)), date(int(year), num, int(d2))
    return None, None


def _deadline(text: str) -> date | None:
    m = _DEADLINE.search(text)
    if not m:
        return None
    day, mon, year = m.groups()
    return date(int(year), _MONTHS[mon.lower()], int(day))
