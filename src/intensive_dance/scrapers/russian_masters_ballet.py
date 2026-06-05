"""Russian Masters Ballet — third scraper, first to exercise teachers + the
`video`/`cv` requirement branches.

API FIRST — but there is none. Unlike RBS and Joffrey (WordPress + REST), RMB
runs on **Bitrix** with no JSON API, no schema.org `ld+json`, and no embedded
state blob, so this is the project's first genuine HTML scrape (selectolax).
The markup is regular enough to read structurally: each location page lays its
programs out as `div.course-city-program[id]` tracks, with a fixed grid of
`block-title`/`block-text` pairs (AIMED AT, DURATION, …) plus a prose article.

DISCOVERY: two course categories — summer (`/courses/summer-intensives/`) and
winter (`/courses/ballet-experience/`, branded "Winter Ballet Intensives"). We
fetch each category index, follow its location children (Alicante, Burgas,
St. Petersburg / Madrid, Perth, Shanghai), and emit **one Offering per track**
on each page. Tracks differ enough — level, ages, fee, and *requirements* — that
folding them into one record would lose information: the dancer tracks
(Professional / Open- / Pre-Professional) require an **audition** (a video being
one accepted form), while the **Observation** track is for ballet teachers and
asks for a **CV**. A location whose header date reads "…CANCELLED" is skipped
whole (mirrors RBS dropping cancelled cycles).

Offering ids are `russian-masters-ballet/{location}-{track}-{season}` (e.g.
`russian-masters-ballet/alicante-professional-2026`), keeping locations, tracks,
and year-over-year cycles distinct and diffable.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-04):
  - TEACHERS with AFFILIATIONS — RMB publishes a named per-track roster linked to
    `/faculty/teachers/…`, each with an institution ("current teacher of Vaganova
    Academy", "former soloist of the Mariinsky Theatre"). This is the named
    roster RBS/Joffrey lacked; we resolve known institutions to `affiliations`.
  - REQUIREMENTS = VIDEO (specific) and CV. The audition video has a *defined
    brief* (set barre/adagio/jumps/pointe combinations) → `video`/`specific`,
    the branch RBS (photos) and Joffrey (video/unspecific) don't reach. The
    Observation track wants a CV → the `cv` branch.
  - PRICES in local currency — EUR (Spain/Russia/Bulgaria) and CNY (Shanghai);
    parsed from the per-track PROGRAM FEE prose.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

import httpx
from selectolax.parser import HTMLParser, Node

from intensive_dance import parse
from intensive_dance.models import (
    Affiliation,
    Application,
    CVReq,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Price,
    Requirement,
    Schedule,
    Source,
    Teacher,
    VideoReq,
    now_utc,
)

BASE = "https://russianmastersballet.com"
REGISTER_URL = f"{BASE}/pages/registration-for-intensives/"

ORG = Organization(
    name="Russian Masters Ballet", slug="russian-masters-ballet", country="ES", city="Alicante"
)

# Course category → the season word used in titles. Summer intensives and the
# winter "Ballet Experience" are the two listings; each links to its locations.
CATEGORIES: dict[str, str] = {
    "summer-intensives": "Summer",
    "ballet-experience": "Winter",
}

# A dancer track is assessed by audition (video being one accepted form, with a
# defined brief); the Observation track (for teachers) asks for a CV instead.
_AUDITION_NOTE = (
    "Applicants pass an audition — live group, online group, online individual, "
    "or by video. A video audition (8–12 min) must show: barre (tendu, fondu, "
    "grand battement); a centre adagio; a pirouette combination; small, medium "
    "and big jump combinations; two combinations on pointe; and an optional "
    "classical variation. Returning RMB students may be exempt."
)
_CV_NOTE = "Observation is aimed at ballet teachers; access is by sending a CV to the course email."


def scrape(client: httpx.Client) -> list[Offering]:
    today = date.today()
    offerings: list[Offering] = []
    for category, season_word in CATEGORIES.items():
        for location in _locations(client, category):
            url = f"{BASE}/courses/{category}/{location}/"
            tree = _fetch(client, url)
            if tree is None:
                continue
            offerings += _page_offerings(tree, url, location, season_word, today)
    offerings.sort(key=lambda o: o.id)
    return offerings


def _fetch(client: httpx.Client, url: str) -> HTMLParser | None:
    resp = client.get(url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return HTMLParser(resp.text)


def _locations(client: httpx.Client, category: str) -> list[str]:
    """Location slugs linked from a category index (e.g. ['alicante', …])."""
    tree = _fetch(client, f"{BASE}/courses/{category}/")
    if tree is None:
        return []
    pattern = re.compile(rf"^/courses/{re.escape(category)}/([a-z0-9][a-z0-9-]*)/?$")
    found: list[str] = []
    for anchor in tree.css("a"):
        # urlsplit().path handles relative, absolute, and protocol-relative hrefs
        # alike and drops the query/fragment — the pattern's ^/courses/ anchor then
        # keeps the match to same-category location links.
        path = urlsplit(anchor.attributes.get("href") or "").path
        match = pattern.match(path)
        if match and match.group(1) not in found:
            found.append(match.group(1))
    return sorted(found)


def _page_offerings(
    tree: HTMLParser, url: str, location: str, season_word: str, today: date
) -> list[Offering]:
    city = _city(tree)
    country = _country(tree)
    type_label = _text(tree.css_first(".course-city-type")) or f"RMB {season_word} Intensive"
    dates_text = _text(tree.css_first(".course-city-programs-header-page-title-date"))

    # A cancelled location ("…CANCELLED") is kept and marked, not dropped; ended
    # cycles are kept too ("past" is derived from the dates, not stored).
    cancelled = "cancel" in dates_text.lower()

    season = _year(dates_text)
    base_year = int(season) if season.isdigit() else None
    fallback_start, fallback_end = _dates(dates_text, base_year)

    offerings: list[Offering] = []
    for prog in tree.css("div.course-city-program"):
        track = prog.attributes.get("id")
        if not track:
            continue
        offerings.append(
            _build_offering(
                prog,
                url,
                location,
                track,
                type_label,
                city,
                country,
                season,
                base_year,
                fallback_start,
                fallback_end,
                cancelled,
            )
        )
    return offerings


def _build_offering(
    prog: Node,
    url: str,
    location: str,
    track: str,
    type_label: str,
    city: str | None,
    country: str | None,
    season: str,
    base_year: int | None,
    fallback_start: date | None,
    fallback_end: date | None,
    cancelled: bool = False,
) -> Offering:
    track_name = (
        _text(prog.css_first(".course-city-program-name")) or track.replace("-", " ").title()
    )
    blocks = _blocks(prog)
    article = prog.css_first(".article-col-right-1.content-text")
    body = _br_text(article) if article is not None else ""

    duration = blocks.get("DURATION", "")
    start, end = _dates(duration, base_year)
    if start is None and end is None:
        start, end = fallback_start, fallback_end

    is_observation = track == "observation" or "cv" in blocks.get("ACCESS", "").lower()
    requirements: list[Requirement] = (
        [CVReq()]
        if is_observation
        else [VideoReq(specificity="specific", description=_AUDITION_NOTE)]
    )

    title = (
        f"{type_label} {city} — {track_name} {season}".strip()
        if city
        else f"{type_label} — {track_name} {season}"
    )

    return Offering(
        id=f"russian-masters-ballet/{location}-{track}-{season}",
        source=Source(provider="russian-masters-ballet", url=f"{url}#{track}", scrapedAt=now_utc()),
        title=title,
        genres=_genres(f"{track_name} {body}"),
        kind="intensive",
        lifecycle="cancelled" if cancelled else "scheduled",
        lifecycleNote="This RMB location has been cancelled." if cancelled else None,
        level=_levels(track_name),
        ageRange=_age_range(blocks.get("AIMED AT", "")),
        organization=ORG,
        location=Location(
            venue=_venue(blocks.get("BALLET FACILITIES")), city=city, country=country
        ),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone=_TIMEZONES.get(country or ""),
            notes=duration or None,
        ),
        teachers=_teachers(article) if article is not None else [],
        prices=_prices(_section(body, "PROGRAM FEE"), country),
        application=Application(
            url=REGISTER_URL,
            requirements=requirements,
            notes=(_CV_NOTE if is_observation else _AUDITION_NOTE),
        ),
    )


# --- header: city / country / season -----------------------------------------

# Country name (as written after the comma in the page H1) → ISO 3166-1 alpha-2,
# with the IANA timezone we tag the schedule with.
_COUNTRIES: dict[str, tuple[str, str]] = {
    "spain": ("ES", "Europe/Madrid"),
    "russia": ("RU", "Europe/Moscow"),
    "bulgaria": ("BG", "Europe/Sofia"),
    "china": ("CN", "Asia/Shanghai"),
    "australia": ("AU", "Australia/Perth"),
}
_TIMEZONES = {iso: tz for iso, tz in _COUNTRIES.values()}


def _city(tree: HTMLParser) -> str | None:
    text = _text(tree.css_first("h1.course-city-programs-header-page-title"))
    return text.split(",")[0].strip() or None if text else None


def _country(tree: HTMLParser) -> str | None:
    text = _text(tree.css_first("h1.course-city-programs-header-page-title")).lower()
    for name, (iso, _tz) in _COUNTRIES.items():
        if name in text:
            return iso
    return None


# --- block grid (AIMED AT / DURATION / …) ------------------------------------


def _venue(text: str | None) -> str | None:
    """Tidy the BALLET FACILITIES value (some inline an 'Address:' label)."""
    if not text:
        return None
    tidy = re.sub(r"\s*Address:\s*", ", ", re.sub(r"\s+", " ", text))
    return tidy.strip(" ,") or None


def _blocks(prog: Node) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in prog.css("div.course-city-program-block"):
        title = block.css_first(".course-city-program-block-title")
        value = block.css_first(".course-city-program-block-text")
        if title and value:
            out[_text(title).upper()] = _text(value)
    return out


# --- prose article ------------------------------------------------------------
#
# The article is free-flowing prose whose section markers are <b> labels — but
# the markup is unreliable (stray/unclosed <b>, names also bolded), so we work on
# the br-aware *text* and slice on the known uppercase labels instead of the DOM.

_LABELS = [
    "COURSE OBJECTIVE",
    "THE PROGRAM INCLUDE",
    "IN ADDITION",
    "TEACHERS",
    "SPECIAL GUESTS",
    "PROGRAM FEE",
    "OFFICIAL ACCOMMODATION",
    "EXTRAS",
    "CANCELATION",
    "ACCESS",
    "INSCRIPTION",
]
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _br_text(node: Node) -> str:
    """Node text with <br> preserved as newlines (so fee lines stay separate)."""
    text = HTMLParser(_BR.sub("\n", node.html or "")).text(separator=" ")
    text = re.sub(r"[ \t]+", " ", text.replace("\xa0", " "))
    return re.sub(r" *\n *", "\n", text).strip()


def _section(text: str, label: str) -> str:
    """The prose between `label` and the next known label (case-insensitive)."""
    low = text.lower()
    start = low.find(label.lower())
    if start < 0:
        return ""
    start += len(label)
    ends = [e for lbl in _LABELS if (e := low.find(lbl.lower(), start)) >= 0]
    return text[start : min(ends)].strip(" :\n-–") if ends else text[start:].strip(" :\n-–")


# --- genres / levels / ages ---------------------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet", "classical", "vaganova", "pas de deux")),
    ("neoclassical", ("neoclassical",)),
    ("contemporary", ("contemporary",)),
    ("character", ("character",)),
    ("repertoire", ("repertoire", "repertory")),
    ("pointe", ("point",)),  # RMB writes "Points" / "Pointe"
]


def _genres(text: str) -> list[Genre]:
    return parse.match_genres(text, _GENRE_KEYWORDS)


def _levels(track_name: str) -> list[Level]:
    low = track_name.lower()
    levels: list[Level] = []
    if "pre-professional" in low or "pre professional" in low:
        levels.append("pre-professional")
    elif "professional" in low:
        levels.append("professional")
    if "open" in low:
        levels.append("open")
    return levels


_AGE = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:y\.?\s?o\.?|years?\s*old|years?)", re.IGNORECASE
)


def _age_range(text: str) -> dict | None:
    bounds = [int(n) for pair in _AGE.findall(text) for n in pair]
    return {"min": min(bounds), "max": max(bounds)} if bounds else None


# --- dates --------------------------------------------------------------------
#
# DURATION reads "3 weeks: 5 - 26 July" / "28 June - 19 July" / "26 December -
# 30 December, 2026"; the year is on the page header, so day-month tokens inherit
# the cycle year. We take the earliest start and latest end across the text.

_DAYMON = re.compile(r"(\d{1,2})\s+(" + parse.MONTHALT + r")(?:,?\s*(20\d\d))?", re.IGNORECASE)
# A shared-month range with the day first, e.g. "5 - 26 July" or "5 - 12 July".
_SHORT = re.compile(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(" + parse.MONTHALT + r")", re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d\d)\b")


def _year(text: str) -> str:
    match = _YEAR.search(text)
    return match.group(1) if match else "unknown"


def _dates(text: str, year: int | None) -> tuple[date | None, date | None]:
    # A year written into the text wins; otherwise inherit the cycle year passed
    # in (the page header carries it when the DURATION line omits it).
    in_text = _YEAR.search(text)
    base = int(in_text.group(1)) if in_text else year

    tokens: list[tuple[int, int, int | None]] = []  # (month, day, explicit year)
    for day, month, yr in _DAYMON.findall(text):
        tokens.append((parse.MONTHS[month.lower()], int(day), int(yr) if yr else None))
    for d1, d2, month in _SHORT.findall(text):
        month_num = parse.MONTHS[month.lower()]
        tokens += [(month_num, int(d1), None), (month_num, int(d2), None)]
    if not tokens:
        return None, None

    # A winter cycle can run backwards across New Year (e.g. 26 December –
    # 4 January): the early-month tail belongs to the next year.
    months = [m for m, _, _ in tokens]
    wraps = max(months) >= 9 and min(months) <= 6
    points: list[date] = []
    for month, day, yr in tokens:
        if yr is not None:
            points.append(date(yr, month, day))
        elif base is not None:
            points.append(date(base + (1 if wraps and month <= 6 else 0), month, day))
    return (min(points), max(points)) if points else (None, None)


# --- prices -------------------------------------------------------------------

_MONEY = re.compile(
    r"(?P<amt>\d[\d., ]*\d|\d)\s*(?P<cur>€|euros?|eur|cny|¥|лв|bgn|₽|rub|aud|usd|\$)",
    re.IGNORECASE,
)
# Unambiguous tokens map straight to ISO 4217.
_CURRENCY = {
    "€": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "eur": "EUR",
    "cny": "CNY",
    "лв": "BGN",
    "bgn": "BGN",
    "₽": "RUB",
    "rub": "RUB",
    "aud": "AUD",
    "usd": "USD",
}
# Bare glyphs that name a different currency depending on where the course runs
# ($ → USD/AUD, ¥ → CNY/JPY). RMB prices each location in its local currency, so
# we resolve the glyph against the offering's country and fall back to the most
# common reading (key None) when the country is unknown.
_SYMBOL_BY_COUNTRY: dict[str, dict[str | None, str]] = {
    "$": {"AU": "AUD", "US": "USD", None: "USD"},
    "¥": {"CN": "CNY", "JP": "JPY", None: "CNY"},
}


def _money(match: re.Match, country: str | None) -> tuple[float, str]:
    amount = float(re.sub(r"[, ]", "", match.group("amt")))
    token = match.group("cur")
    by_country = _SYMBOL_BY_COUNTRY.get(token)
    if by_country is not None:
        return amount, by_country.get(country, by_country[None])
    return amount, _CURRENCY[token.lower()]


def _prices(fee_text: str, country: str | None) -> list[Price]:
    """Fees written as prose, one option per line: '2 weeks: … - 950 €'.

    The label is the text just before the amount (after the last ':' or '-');
    the whole line is kept in `notes`. Lines without a money token are skipped.
    `country` disambiguates bare currency glyphs (see _SYMBOL_BY_COUNTRY).
    """
    prices: list[Price] = []
    for raw in fee_text.split("\n"):
        line = re.sub(r"\s+", " ", raw).strip()
        matches = list(_MONEY.finditer(line))
        for i, match in enumerate(matches):
            start = matches[i - 1].end() if i else 0
            label = line[start : match.start()].strip(" :–-") or "Program fee"
            amount, currency = _money(match, country)
            prices.append(
                Price(
                    amount=amount, currency=currency, label=label, includes=["tuition"], notes=line
                )
            )
    return prices


# --- teachers + affiliations --------------------------------------------------
#
# Resident faculty are anchors to /faculty/teachers/<slug>/; featured guests are
# anchors to /faculty/artists/ (or /faculty/guests/) in the "Special guests"
# block. Both are followed by a prose description ("current teacher of Vaganova
# Academy"). We walk the article in document order — not by DOM siblings —
# because the first names are nested in wrapper <span>s, so a sibling walk
# overruns into the next teacher. Known institutions in the description become
# `affiliations`; guests are emitted as ordinary teachers tagged role="guest".

# Description substring → (canonical organization, slug | None).
_INSTITUTIONS: list[tuple[str, str, str | None]] = [
    ("vaganova", "Vaganova Ballet Academy", "vaganova-ballet-academy"),
    ("bolshoi", "Bolshoi Ballet Academy", "bolshoi-ballet-academy"),
    ("eifman", "Boris Eifman Dance Academy", None),
    ("mariinsky", "Mariinsky Theatre", None),
    ("mikhailovsky", "Mikhailovsky Theatre", None),
    ("royal swedish", "Royal Swedish Ballet", None),
    ("dutch national", "Dutch National Ballet", None),
    ("national opera of ukraine", "National Opera of Ukraine", None),
    ("deutsche oper", "Deutsche Oper am Rhein", None),
    ("bristol russian", "Bristol Russian Ballet School", None),
    ("rmb", "Russian Masters Ballet", "russian-masters-ballet"),
    ("russian masters", "Russian Masters Ballet", "russian-masters-ballet"),
]
_PAST = ("ex ", "ex-", "former", "graduate", "graduated", "retired")
_PRESENT = (
    "current",
    "permanent",
    "principal",
    "senior",
    "director",
    "licensed",
    "general methodist",
)
_ROLES = [
    "principal dancer",
    "principal tutor",
    "principal",
    "soloist",
    "choreographer",
    "director",
    "general methodist",
    "methodist",
    "senior teacher",
    "tutor",
    "teacher",
]


def _teachers(article: Node) -> list[Teacher]:
    teachers: dict[str, Teacher] = {}
    for name, desc, role in _teacher_entries(article):
        if not name or name.lower() in {"teachers", "teacher"}:
            continue
        teacher = Teacher(name=name, role=role, affiliations=_affiliations(desc))
        prior = teachers.get(name)
        if prior is None or _prefer(teacher, prior):
            teachers[name] = teacher
    return list(teachers.values())


def _prefer(new: Teacher, prior: Teacher) -> bool:
    """Whether `new` should replace an already-seen entry for the same person.

    Resident faculty (role "teacher") wins over a "guest" listing of the same
    person; within one role, a description carrying affiliations beats a bare name.
    """
    if new.role != prior.role:
        return new.role == "teacher"
    return not prior.affiliations and bool(new.affiliations)


# Faculty link path → the role the listed person takes in this intensive.
_FACULTY_ROLES = (
    ("/faculty/teachers/", "teacher"),
    ("/faculty/artists/", "guest"),
    ("/faculty/guests/", "guest"),
)


def _faculty_role(href: str) -> str | None:
    return next((role for path, role in _FACULTY_ROLES if path in href), None)


def _teacher_entries(article: Node) -> list[tuple[str, str, str]]:
    """(name, description, role) per faculty anchor, in document order.

    Captures resident faculty (`/faculty/teachers/`) and featured guests
    (`/faculty/artists/`, `/faculty/guests/`); the description runs to the next
    faculty anchor or line break.
    """
    entries: list[list[str]] = []  # [name, desc, role] accumulators
    current: list[str] | None = None

    def walk(node: Node) -> None:
        nonlocal current
        for child in node.iter(include_text=True):
            tag = child.tag
            href = (child.attributes.get("href") or "") if tag == "a" else ""
            if tag == "a" and (role := _faculty_role(href)):
                if current is not None and role == current[2] and not current[1].strip():
                    # a name split across adjacent faculty links (only whitespace
                    # between them, no description yet) — same person, one entry
                    current[0] = f"{current[0]} {_text(child)}".strip()
                else:
                    current = [_text(child), "", role]
                    entries.append(current)
            elif tag == "a" and "/faculty/" in href:
                current = None  # an unrelated faculty link (index/team) closes the entry
            elif tag == "br":
                current = None  # the description ends at the line break
            elif tag == "-text":
                if current is not None:
                    current[1] += child.text()
            else:
                walk(child)

    walk(article)
    return [(name, _clean_desc(desc), role) for name, desc, role in entries]


def _clean_desc(desc: str) -> str:
    desc = parse.clean(desc).split("*")[0]  # drop the trailing "*names may vary" disclaimer
    return desc.strip(" -–,")


def _affiliations(desc: str) -> list[Affiliation]:
    # Emitted in _INSTITUTIONS table order, not the order the institutions appear
    # in the bio — so the order is stable across scrapes but carries no "primary
    # affiliation" meaning. Don't read affiliations[0] as the person's main house.
    low = desc.lower()
    orgs: list[tuple[str, str | None]] = []
    for needle, org, slug in _INSTITUTIONS:
        if needle in low and not any(org == o for o, _ in orgs):
            orgs.append((org, slug))
    if not orgs:
        return []
    # Role/currency can only be attributed confidently when one institution is named.
    role = current = None
    if len(orgs) == 1:
        role = next((r for r in _ROLES if r in low), None)
        if any(p in low for p in _PAST):
            current = False
        elif any(p in low for p in _PRESENT):
            current = True
    return [
        Affiliation(organization=org, slug=slug, role=role, current=current) for org, slug in orgs
    ]


def _text(node: Node | None) -> str:
    return parse.clean(node.text()) if node is not None else ""
