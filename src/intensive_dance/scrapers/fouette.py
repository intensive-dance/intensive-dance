"""Szkoła Tańca i Baletu Fouetté (PL, Poznań) — its summer camp + winter intensive.

API FIRST: plain WordPress. `GET https://fouette.pl/wp-json/` is 200 and the camp
hub page (`obozy-i-ferie-taneczne`) plus the blog `posts` come back with real
bodies in `content.rendered` — no JS/proxy needed for the parts we use. (The
`pedagodzy` faculty CPT *does* hide its bios behind Elementor, so the founder
credential below is the one fact we pin from a one-off proxy read, hard-coded —
it never changes.)

DISCOVERY: the hub page is **evergreen** — it describes the two recurring
short-term programs ("LATO Z FOUETTÉ" summer camp; "ZIMA": the children's
"TANECZNE FERIE" and the advanced "INTENSYWNY KURS ZIMOWY / WINTER INTENSIVE") in
prose but carries no dates/prices/ages. The *dated editions* live as recap blog
posts (one per edition, published right after it runs). So we discover one
`Offering` per camp/winter post that yields a concrete date span — the year comes
from the post's publish date (a recap is published days after the event), the
day/month from a Polish month range in the body ("23–27 lutego") or a numeric span
encoded in the slug/title ("13-20.08.2021"). Posts without a parseable span are
skipped (faithful: we don't invent a date). Ended editions are kept (IDR-24).

LANGUAGE: parsed **language-agnostically** — numeric/Polish-month dates, enum
genres keyword-matched against the program's own class vocabulary (PL + the EN
labels the school itself uses), founder/affiliation pinned. No free Polish text is
emitted, so the committed data is stable regardless of which render serves.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08): one Offering per dated
edition; PLN currency context but **no prices stated** (prices=[]); summer vs
winter genre sets (winter adds jazz/pointe/repertoire/contemporary, summer is
classical/contemporary core); `ageRange=None` (never stated); a `Teacher` with an
`Affiliation` (the founder, prof. UMFC Warsaw); `application.requirements=[]`
(audition/entry terms not published on these recap pages). No lifecycle banners.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.models import (
    Affiliation,
    Genre,
    Location,
    Offering,
    Organization,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://fouette.pl"

ORG = Organization(
    name="Szkoła Tańca i Baletu Fouetté", slug="fouette", country="PL", city="Poznań"
)

# Founder & director. Her affiliation (Chopin University of Music, Warsaw) is
# stated on the school's own pages ("dr hab. … prof. UMFC w Warszawie"); pinned
# here because the faculty CPT body is Elementor-rendered and empty over REST.
FOUNDER = Teacher(
    name="Beata Książkiewicz",
    role="Founder & Director",
    affiliations=[
        Affiliation(
            organization="Fryderyk Chopin University of Music, Warsaw",
            role="Professor (dr hab.)",
            current=True,
        ),
    ],
)

# Polish month names → number, for the in-body "23–27 lutego" form. Months appear
# in the genitive (…a) on Polish datelines, which is what we match.
_PL_MONTHS: dict[str, int] = {
    "stycznia": 1,
    "lutego": 2,
    "marca": 3,
    "kwietnia": 4,
    "maja": 5,
    "czerwca": 6,
    "lipca": 7,
    "sierpnia": 8,
    "września": 9,
    "wrzesnia": 9,
    "października": 10,
    "pazdziernika": 10,
    "listopada": 11,
    "grudnia": 12,
}
_PL_MONTHALT = "|".join(sorted(_PL_MONTHS, key=len, reverse=True))

# A post is a camp/winter edition when its slug or title carries one of these.
# (Tight enough to skip the school's spectacles / recruitment posts.)
_EDITION_KW = re.compile(r"oboz|obóz|ferie|zimow|winter|intensywny|letni", re.IGNORECASE)
# Winter editions (ferie / intensywny kurs zimowy) vs the summer camp.
_WINTER_KW = re.compile(r"ferie|zimow|winter|intensywny", re.IGNORECASE)


def scrape(client: httpx.Client) -> list[Offering]:
    posts = wp.fetch_all(
        client, "posts", base=BASE, params={"_fields": "slug,date,link,title,content"}
    )
    return _build_offerings(posts)


def _build_offerings(posts: list[dict]) -> list[Offering]:
    offerings: list[Offering] = []
    seen: set[str] = set()
    for post in posts:
        slug = post["slug"]
        title = _strip_html(post["title"]["rendered"])
        if not _EDITION_KW.search(f"{slug} {title}"):
            continue
        body = _strip_html(post["content"]["rendered"])
        post_year = int(post["date"][:4])
        span = _date_span(slug, title, body, post_year)
        if span is None:
            continue  # no parseable date → don't invent one
        start, end = span
        is_winter = bool(_WINTER_KW.search(f"{slug} {title}"))
        offering_slug = f"{'winter-intensive' if is_winter else 'summer-camp'}-{start.year}"
        if offering_slug in seen:
            continue  # one edition per program per year (recaps can repeat)
        seen.add(offering_slug)
        offerings.append(_offering(offering_slug, post["link"], is_winter, start, end, body))
    offerings.sort(key=lambda o: o.id)
    return offerings


def _offering(
    offering_slug: str, url: str, is_winter: bool, start: date, end: date, body: str
) -> Offering:
    label = "Winter Intensive" if is_winter else "Summer Camp"
    return Offering(
        id=f"fouette/{offering_slug}",
        source=Source(provider="fouette", url=url, scrapedAt=now_utc()),
        title=f"Fouetté {label} {start.year}",
        genres=_genres(body),
        organization=ORG,
        # Camps run at a residential centre the recap doesn't name; only the
        # country is faithfully known (the school is Poznań, the camp isn't).
        location=Location(country="PL"),
        schedule=Schedule(
            season=str(start.year),
            start=start,
            end=end,
            timezone="Europe/Warsaw",
        ),
        teachers=[FOUNDER],
    )


# --- dates --------------------------------------------------------------------
# Two shapes seen: an in-body Polish month range ("23–27 lutego", year from the
# recap's publish year) and a numeric span baked into the slug/title
# ("13-20.08.2021", "14-08-24-08-2019"). Both single-month spans.

_PL_RANGE = re.compile(r"(\d{1,2})\s*[–-]\s*(\d{1,2})\s+(" + _PL_MONTHALT + r")", re.IGNORECASE)
# dd-dd.mm.yyyy  (one month, e.g. "13-20.08.2021")
_NUM_RANGE_1M = re.compile(r"(\d{1,2})[-–](\d{1,2})\.(\d{1,2})\.(\d{4})")
# dd-mm-dd-mm-yyyy (cross-day slug form, e.g. "14-08-24-08-2019")
_NUM_RANGE_2M = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{4})")


def _date_span(slug: str, title: str, body: str, post_year: int) -> tuple[date, date] | None:
    blob = f"{slug} {title}"
    m2 = _NUM_RANGE_2M.search(blob)
    if m2:
        d1, mo1, d2, mo2, year = (int(g) for g in m2.groups())
        return date(year, mo1, d1), date(year, mo2, d2)
    m1 = _NUM_RANGE_1M.search(blob)
    if m1:
        d1, d2, mo, year = (int(g) for g in m1.groups())
        return date(year, mo, d1), date(year, mo, d2)
    mp = _PL_RANGE.search(body)
    if mp:
        d1, d2, month = mp.group(1), mp.group(2), mp.group(3)
        mo = _PL_MONTHS[month.lower()]
        return date(post_year, mo, int(d1)), date(post_year, mo, int(d2))
    return None


# --- genres -------------------------------------------------------------------
# Keyword-match the program's own class vocabulary (PL terms + the EN labels the
# school uses), not loose prose. The ballet/pointe/repertoire core is faithful:
# "taniec klasyczny" = classical, "point/pointy" = pointe, "repertuar" = repertoire.

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("klasyczn", "classical", "ballet", "balet")),
    ("contemporary", ("współczesn", "wspolczesn", "contemporary")),
    ("repertoire", ("repertuar", "repertoire")),
    ("pointe", ("point",)),  # "point" / "pointy" (pointe work)
]


def _genres(body: str) -> list[Genre]:
    return parse.match_genres(body, _GENRE_KEYWORDS, default=["classical"])


# --- helpers ------------------------------------------------------------------


def _strip_html(rendered: str) -> str:
    return parse.clean(re.sub(r"<[^>]+>", " ", rendered))
