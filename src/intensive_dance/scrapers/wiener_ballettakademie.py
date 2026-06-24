"""Wiener Ballettakademie (Vienna, AT) — its Intensive Ballet Masterclass.

API FIRST: none usable. The site (wienerballettakademie.com) is a **base44
React SPA** — `/wp-json/` is absent, there is no `Event`/`Course` `ld+json`
(only generic SEO meta), and the program data is fetched client-side from the
base44 backend (no inline state blob in the static HTML). So we read the
**stealth-rendered** DOM, not raw markup.

FETCH: every request forces the proxy's `render=1` tier via `PROXY_PARAMS_HEADER`
(the SPA renders nothing without JS); the header is inert on a direct dev fetch.

DISCOVERY: one dated edition. The provider advertises several program pages
(`/SummerIntensive`, `/InternationalSummerSchool`, `/HolidayIntensive`,
`/WinterIntensive`, `/SpringWorkshop`), but as of June 2026 only `/SummerIntensive`
carries a concrete, dated, public edition — the **Intensive Ballet Masterclass
2026** (24–30 Aug 2026). The others are "TBC" / "in planning" / "register your
interest" (International Summer School 2027, Winter Intensive 2026, Spring
Workshop Series 2027) or an undated recurring children's holiday course
(Ferienkurse) — none emit an Offering until they state real dates. This re-verifies
the earlier "pre-launch — all TBC" deferral, now stale (#362). We scrape the one
Masterclass page and emit a single Offering; its three booking tiers (full
masterclass / + individual lessons / individual-lessons-only) are `prices`, not
separate offerings — same dated event.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-23):
  - Single-edition render guard: a fetch lacking the "Intensive Ballet
    Masterclass <year>" marker (challenge / partial render) RAISES rather than
    returning [] — so a transient blip can't wipe the committed edition (IDR-24).
  - DATES: a single-month span "24 – 30 August 2026" → start/end.
  - AGES: open-topped "ages 15 and above" → {min: 15, max: null}.
  - LEVEL: ["advanced", "professional"] from "advanced students & professionals".
  - GENRES: classical / repertoire / pointe / contemporary, matched against the
    stated curriculum ("Classical Ballet, Repertoire & Pas de Deux", "Pointe &
    Contemporary classes"), not loose prose.
  - PRICES: three EUR tiers parsed structurally from the pricing cards
    (label / "€ amount" / "Deposit to secure: € amount"), each with its deposit.
  - TEACHERS: the six named faculty (single-purpose masterclass page → safe to
    attribute), with affiliations to the Vienna State Ballet / Vienna State Opera
    where stated — including a *former* principal (current=False) from a
    "(2005–2020)" tenure.
  - APPLICATION: open enrolment by deposit, no submission material → [NoneReq].
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.fetch import PROXY_PARAMS_HEADER
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://wienerballettakademie.com"
PAGE = f"{BASE}/SummerIntensive"
APPLY_URL = f"{BASE}/Contact?type=enrollment&program=summer_intensive_2026"

# The SPA renders nothing without JS, so force the proxy's stealth render tier.
# Inert on a direct (dev) fetch — the transport strips the header.
_RENDER = {PROXY_PARAMS_HEADER: "render=1&wait=9000"}

ORG = Organization(
    name="Wiener Ballettakademie", slug="wiener-ballettakademie", country="AT", city="Vienna"
)
VENUE = Location(venue="Wiener Ballettakademie", city="Vienna", country="AT")

# The dated-edition marker; its absence means a degraded render (see docstring).
_TITLE = re.compile(r"Intensive Ballet Masterclass\s+(\d{4})")


def scrape(client: httpx.Client) -> list[Offering]:
    resp = client.get(PAGE, headers=_RENDER)
    resp.raise_for_status()
    return [_build_offering(_text(resp.text))]


def _text(html: str) -> str:
    """Rendered DOM → newline-separated visible text (one source line per line)."""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    body = tree.body.text(separator="\n") if tree.body else ""
    return "\n".join(parse.clean(line) for line in body.splitlines() if parse.clean(line))


def _build_offering(text: str) -> Offering:
    m = _TITLE.search(text)
    if m is None:
        # Single-edition page: a render missing the marker is degraded, not empty.
        raise ValueError("Wiener Ballettakademie: masterclass marker not found (degraded render?)")
    year = m.group(1)
    start, end, notes = _dates(text, year)
    return Offering(
        id=f"wiener-ballettakademie/intensive-ballet-masterclass-{year}",
        source=Source(provider="wiener-ballettakademie", url=PAGE, scrapedAt=now_utc()),
        title=f"Intensive Ballet Masterclass {year}",
        genres=_genres(text),
        level=_levels(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=VENUE,
        schedule=Schedule(season=year, start=start, end=end, timezone="Europe/Vienna", notes=notes),
        teachers=_teachers(text),
        prices=_prices(text),
        application=Application(
            status="open",
            url=APPLY_URL,
            requirements=[NoneReq()],
            notes=(
                "Open enrolment for advanced students & professionals; secure a place "
                "by paying a deposit, with the balance due 30 days before the start date."
            ),
        ),
    )


# --- dates: "24 – 30 August 2026" (one month/year shared across the span) ---

_DATES = re.compile(
    r"(\d{1,2})\s*[–-]\s*(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _dates(text: str, year: str) -> tuple[date | None, date | None, str | None]:
    m = _DATES.search(text)
    if m is None:
        return None, None, None
    d1, d2, mon, yr = m.groups()
    month = parse.MONTHS[mon.lower()]
    start = date(int(yr), month, int(d1))
    end = date(int(yr), month, int(d2))
    return start, end, parse.clean(m.group(0))


_AGE = re.compile(r"ages?\s+(\d{1,2})\s*(?:\+|and\s+above|or\s+above)", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    m = _AGE.search(text)
    return {"min": int(m.group(1)), "max": None} if m else None


def _levels(text: str) -> list:
    low = text.lower()
    levels = []
    if re.search(r"\badvanced\b", low):
        levels.append("advanced")
    if re.search(r"\bprofessional", low):
        levels.append("professional")
    return levels


_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("classical ballet", "ballet technique")),
    ("repertoire", ("repertoire", "variation", "swan lake")),
    ("pointe", ("pointe",)),
    ("contemporary", ("contemporary",)),
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS, default=["classical"])


# --- prices: card label, then "€ amount", then "Deposit to secure: € amount" ---

_DEPOSIT = re.compile(r"Deposit to secure:\s*€\s*([\d.,]+)", re.IGNORECASE)
_AMOUNT = re.compile(r"(?:from\s+)?€\s*([\d.,]+)", re.IGNORECASE)


def _prices(text: str) -> list[Price]:
    lines = text.splitlines()
    prices: list[Price] = []
    for i, line in enumerate(lines):
        dep = _DEPOSIT.search(line)
        if dep is None or i < 2:
            continue
        amt = _AMOUNT.fullmatch(lines[i - 1].strip())
        if amt is None:
            continue
        amount = parse.parse_amount(amt.group(1))
        deposit = parse.parse_amount(dep.group(1))
        if amount is None:
            continue
        label = lines[i - 2].strip()
        note = f"Deposit to secure: €{int(deposit)}." if deposit is not None else None
        if lines[i - 1].strip().lower().startswith("from"):
            note = f"From €{int(amount)} per lesson. " + (note or "")
        prices.append(
            Price(amount=amount, currency="EUR", label=label, includes=["tuition"], notes=note)
        )
    return prices


# --- teachers: a Title-case name line immediately followed by a "· "-credential ---

_NAME = r"[A-ZÀ-Ýİ][\wÀ-ÿçğı'’-]+(?:\s+[A-ZÀ-Ýİ][\wÀ-ÿçğı'’-]+){1,2}"
_NAME_LINE = re.compile(r"^" + _NAME + r"$")
_PAST_TENURE = re.compile(r"\(\s*\d{4}\s*[–-]\s*\d{4}\s*\)")


def _teachers(text: str) -> list[Teacher]:
    lines = text.splitlines()
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for i in range(len(lines) - 1):
        name = lines[i].strip()
        cred = lines[i + 1].strip()
        if "·" not in cred or not _NAME_LINE.match(name) or name in seen:
            continue
        # The credential always carries a dancer/teacher role keyword; this rejects
        # nav/heading look-alikes ("All Faculty", "World-Class Faculty").
        if not re.search(r"soloist|ballerina|principal|dancer|teacher", cred, re.IGNORECASE):
            continue
        seen.add(name)
        teachers.append(Teacher(name=name, role="faculty", affiliations=_affiliations(cred)))
    return teachers


def _affiliations(cred: str) -> list[Affiliation]:
    title = parse.clean(cred.split("·")[0])
    current = not _PAST_TENURE.search(cred)
    if re.search(r"vienna state ballet|wiener staatsballett", cred, re.IGNORECASE):
        return [
            Affiliation(
                organization="Wiener Staatsballett",
                slug="wiener-staatsballett",
                role=title,
                current=current,
            )
        ]
    if re.search(r"vienna state opera|wiener staatsoper", cred, re.IGNORECASE):
        return [Affiliation(organization="Vienna State Opera", role=title, current=current)]
    return []
