"""Ballet Summer Course Budapest (HU) — an open-enrolment summer intensive split
into age/skill *groups*, each its own Offering.

API FIRST: the site is WordPress (`/wp-json/` 200). The dated edition lives on the
front page (a Page whose body the home URL renders verbatim) and each group's fee
lives on its own group Page. We don't need a custom post type — the home HTML
already lists every group with its name + age band inline in the "Details" link,
plus the course dates and the faculty roster, so we read the home HTML
structurally and follow each "Details" link for that group's fee. The home Page's
own slug is an evergreen oddity (`ballet-summer-course-2017-2`), so we anchor on
the home URL, not a slug — the dated title ("Ballet Summer Course 2026") and the
"held from 27 July 2026 to 8 August 2026" line carry the cycle.

DISCOVERY: one Offering per **group** (level). The seven 2026 groups —
Professional young, Professional, Amateur advanced / intermediate / beginning,
Junior, Children — differ in level, age band, fee and class breakdown, so folding
them would lose information. Each group's age band is stated canonically (English)
in its home-page link label; its fee (€, 1-week and 2-week options) is on its
group page. The whole course runs the same fortnight, so all groups share the
schedule. Ids are `ballet-summer-course-budapest/{group-slug}-{season}`.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-09):
  - One provider, many per-level Offerings sharing one date range (like RMB tracks).
  - Open-ended age bands: "from 16 years of age" and the "no age limit" amateur
    groups keep a null upper bound (`{"min": 16}` / no max); the numeric
    children/junior bands stay numeric.
  - Multiple EUR Prices per Offering (1-week + 2-week tuition options), parsed
    from prose fee lines.
  - TEACHERS with AFFILIATIONS — the home roster names each master with a bio; we
    resolve known houses (Hungarian State Opera / Hungarian National Ballet,
    Mariinsky, Perm Ballet, …) to `affiliations`.
  - Requirements = [] (not stated): open enrolment, no audition/photo/video.
"""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://balletsummercoursebudapest.com"
HOME = f"{BASE}/"

ORG = Organization(
    name="Ballet Summer Course Budapest",
    slug="ballet-summer-course-budapest",
    country="HU",
    city="Budapest",
)


def scrape(client: httpx.Client) -> list[Offering]:
    home = client.get(HOME)
    home.raise_for_status()
    group_html: dict[str, str] = {}
    for url in _group_links(home.text):
        resp = client.get(url)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        group_html[url] = resp.text
    return _build_offerings(home.text, group_html, date.today())


def _build_offerings(home_html: str, group_html: dict[str, str], today: date) -> list[Offering]:
    tree = HTMLParser(home_html)
    start, end = _dates(_home_text(tree))
    anchor = end or start
    season = str(anchor.year) if anchor else "unknown"
    teachers = _teachers(tree)

    offerings: list[Offering] = []
    for name, age_label, url in _groups(tree):
        slug = _slug(url)
        fees_text = _group_fee_text(group_html.get(url, ""))
        offerings.append(
            Offering(
                id=f"ballet-summer-course-budapest/{slug}-{season}",
                source=Source(
                    provider="ballet-summer-course-budapest", url=url, scrapedAt=now_utc()
                ),
                title=f"Ballet Summer Course Budapest — {name} {season}".strip(),
                genres=list(_GENRES),
                level=_levels(name, age_label),
                ageRange=_age_range(age_label),
                organization=ORG,
                location=Location(city="Budapest", country="HU"),
                schedule=Schedule(season=season, start=start, end=end, timezone="Europe/Budapest"),
                teachers=teachers,
                prices=_prices(fees_text),
                application=Application(url=url),
            )
        )
    offerings.sort(key=lambda o: o.id)
    return offerings


# --- home page text / groups --------------------------------------------------
#
# The front page lists each group as an anchor whose label reads
# "Professional young group (from 13 to 15 age) >> Details" and whose href is the
# group's own page. We read the (name, age-label, url) triples from those anchors,
# dropping the "About our groups" index link (no age band, not a group).

_GROUP_HREF = re.compile(r"^" + re.escape(BASE) + r"/(?:about-our-groups/)?[a-z0-9-]+/$")


def _home_text(tree: HTMLParser) -> str:
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _group_links(home_html: str) -> list[str]:
    return [url for _name, _age, url in _groups(HTMLParser(home_html))]


def _groups(tree: HTMLParser) -> list[tuple[str, str, str]]:
    """(group name, raw age-label text, url) per 'Details' link, in page order."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for anchor in tree.css("a"):
        href = anchor.attributes.get("href") or ""
        label = parse.clean(anchor.text())
        if "Details" not in label or not _GROUP_HREF.match(href) or href in seen:
            continue
        seen.add(href)
        # "Professional young group (from 13 to 15 age) >> Details" → name, age band.
        head = re.split(r">>\s*Details", label)[0].strip(" .")
        bracket = re.search(r"\(([^)]*)\)", head)
        name = re.sub(r"\s*\([^)]*\)\s*$", "", head).strip(" .")
        out.append((name, bracket.group(1) if bracket else "", href))
    return out


def _slug(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


# --- dates: "held from 27 July 2026 to 8 August 2026" --------------------------

_DATE_RANGE = re.compile(
    r"(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})\s+to\s+"
    r"(\d{1,2})\s+(" + parse.MONTHALT + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _dates(text: str) -> tuple[date | None, date | None]:
    m = _DATE_RANGE.search(text)
    if not m:
        return None, None
    d1, mon1, y1, d2, mon2, y2 = m.groups()
    start = date(int(y1), parse.MONTHS[mon1.lower()], int(d1))
    end = date(int(y2), parse.MONTHS[mon2.lower()], int(d2))
    return start, end


# --- ages: from the group's link label ----------------------------------------
# "from 13 to 15 age" → 13-15 · "from 16 years of age" → {16, open} ·
# "between 8 and 10 years of age" → 8-10 · "no age limit" → open both ends (None).

_AGE_RANGE = re.compile(r"(?:from|between)\s+(\d{1,2})\s+(?:to|and|-)\s+(\d{1,2})", re.IGNORECASE)
_AGE_FROM = re.compile(r"from\s+(\d{1,2})\b", re.IGNORECASE)


def _age_range(label: str) -> dict | None:
    m = _AGE_RANGE.search(label)
    if m:
        return {"min": int(m.group(1)), "max": int(m.group(2))}
    m = _AGE_FROM.search(label)
    if m:
        return {"min": int(m.group(1))}  # open-topped ("from 16 years of age")
    return None  # "no age limit" → no stated bounds


# --- levels -------------------------------------------------------------------


def _levels(name: str, age_label: str) -> list[Level]:
    low = f"{name} {age_label}".lower()
    levels: list[Level] = []
    if "professional" in low:
        levels.append("professional")
    if "advanced" in low:
        levels.append("advanced")
    if "intermediate" in low:
        levels.append("intermediate")
    if "beginning" in low or "beginner" in low:
        levels.append("beginner")
    # Amateur groups ("no age limit") are open to any hobby dancer.
    if "amateur" in low or "no age limit" in low:
        levels.append("open")
    return levels


# --- prices: group-page fee lines ("1 week: 450 €", "2 weeks: 750 €") ----------
#
# Fees live only on the group page. The tuition options read "<N> week(s): <amt>
# €"; we read those from the whole page body. (The bare word "Fees" can't anchor a
# slice — it also appears in the nav menu.) The optional children "extra class"
# fee is written amount-first ("80 € for 1 week (6 hours)"), so we truncate the
# text at that marker before scanning — a week-token can otherwise sit just before
# the extra-class amount and read as tuition.

_FEE_LINE = re.compile(r"(\d\s*weeks?)\s*[:\-]?\s*(\d[\d.,\s]*?)\s*€", re.IGNORECASE)


def _group_fee_text(html: str) -> str:
    if not html:
        return ""
    tree = HTMLParser(html)
    for node in tree.css("script, style, noscript"):
        node.decompose()
    return parse.clean(tree.body.text(separator=" ")) if tree.body else ""


def _prices(fee_text: str) -> list[Price]:
    cut = re.split(r"extra\s+class", fee_text, maxsplit=1, flags=re.IGNORECASE)[0]
    prices: list[Price] = []
    for span, amount_raw in _FEE_LINE.findall(cut):
        amount = parse.parse_amount(amount_raw)
        if amount is None or amount < 50:
            continue
        label = parse.clean(span).lower()
        prices.append(
            Price(
                amount=amount,
                currency="EUR",
                label=label,
                includes=["tuition"],
                notes=f"{label}: {parse.clean(amount_raw)} €",
            )
        )
    return prices


# --- genres -------------------------------------------------------------------
#
# The front page states the curriculum once for the whole course ("Classical
# ballet, pointe work, variation, virtuosity, character dance, modern
# (contemporary), pilates and stretching"); every group draws from it, so the
# genre set is shared. Pilates/stretching/virtuosity aren't ballet *genres*.

_GENRES: tuple[Genre, ...] = ("classical", "pointe", "repertoire", "character", "contemporary")


# --- teachers + affiliations --------------------------------------------------
#
# The "Our teachers" block names each master in a heading anchor (linking to their
# bio page), followed by a prose bio. We read the heading names and slice each bio
# up to the next teacher heading, resolving known houses in the bio to
# affiliations. Names are kept verbatim (the site mixes "Surname Given" order).

_INSTITUTIONS: list[tuple[str, str]] = [
    ("hungarian state opera", "Hungarian State Opera"),
    ("hungarian national ballet institute", "Hungarian National Ballet Institute"),
    ("hungarian national ballet", "Hungarian National Ballet"),
    ("hungarian dance academy", "Hungarian Dance Academy"),
    ("mariinsky", "Mariinsky Theatre"),
    ("perm ballet", "Perm Ballet"),
    ("bolshoi", "Bolshoi Ballet"),
    ("national opera of ukraine", "National Opera of Ukraine"),
    ("imperial russian ballet", "Imperial Russian Ballet"),
    ("gitis", "GITIS (Russian Institute of Theatre Arts)"),
]


def _teachers(tree: HTMLParser) -> list[Teacher]:
    headings = _teacher_headings(tree)
    if not headings:
        return []
    body = _home_text(tree)
    low = body.lower()
    teachers: list[Teacher] = []
    seen: set[str] = set()
    for i, name in enumerate(headings):
        if name in seen:
            continue
        seen.add(name)
        start = low.find(name.lower())
        nxt = -1
        if start >= 0:
            for other in headings[i + 1 :]:
                nxt = low.find(other.lower(), start + len(name))
                if nxt >= 0:
                    break
        bio = (
            body[start:nxt] if start >= 0 and nxt > start else (body[start:] if start >= 0 else "")
        )
        teachers.append(Teacher(name=name, affiliations=_affiliations(bio)))
    return teachers


def _teacher_headings(tree: HTMLParser) -> list[str]:
    """Teacher names from the headings under 'Our teachers', in page order.

    Each teacher is a heading (h2-h5) wrapping an anchor to their bio page; the
    block starts at the 'Our teachers' heading.
    """
    names: list[str] = []
    collecting = False
    for node in tree.css("h1, h2, h3, h4, h5"):
        text = parse.clean(node.text())
        if not text:
            continue
        if text.lower() == "our teachers":
            collecting = True
            continue
        if not collecting:
            continue
        anchor = node.css_first("a")
        href = (anchor.attributes.get("href") or "") if anchor is not None else ""
        # A teacher heading links to a /<name>/ bio page (not a group / wp-content).
        if anchor is None or "/about-our-groups" in href or "/wp-content/" in href:
            continue
        name = parse.clean(anchor.text())
        if name and name.lower() != "our teachers":
            names.append(name)
    return names


_PAST = ("former", "graduate", "graduated", "ex-", "ex ")
_PRESENT = ("since", "current", "present", "member of the hungarian")


def _affiliations(bio: str) -> list[Affiliation]:
    low = bio.lower()
    out: list[Affiliation] = []
    for needle, org in _INSTITUTIONS:
        if needle in low and not any(a.organization == org for a in out):
            current: bool | None = None
            if any(p in low for p in _PRESENT):
                current = True
            elif any(p in low for p in _PAST):
                current = False
            out.append(Affiliation(organization=org, current=current))
    return out
