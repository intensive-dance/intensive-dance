"""Associazione Europea Danza — Summer Dance School, Livorno IT.

API FIRST: WordPress with `/wp-json/`, but the whole site sits behind a
Cloudflare challenge that 403s the proxy's plain *and* `auto` tiers — only the
FlareSolverr `solve=1` tier returns the REST JSON. That tier hands back the
*rendered DOM*, so the JSON arrives wrapped in Chromium's JSON viewer (the body
sits inside `<pre>`, HTML-escaped) **and** Cloudflare's email-protection script
has injected real `<a class="__cf_email__">` tags into every displayed email,
corrupting the JSON. `wp.fetch_*` can't help (they call `resp.json()`), so we
fetch with `solve=1` forced via `PROXY_PARAMS_HEADER` and unwrap by hand: legit
JSON angle-brackets are escaped (`&lt;`/`&gt;`), so the only *real* tags inside
the `<pre>` are CF's injections — strip them, then unescape the structural
entities and `json.loads` (see `_unwrap`).

DISCOVERY: the site is mostly out of scope — CND/Eurocity dance *competitions*
(icebox #80), teacher-bio posts, other schools' auditions (Codarts, Royal Ballet
School, Marseille) and galas. The one in-scope item is the org's own dated
**Summer Dance School Livorno** (post 9401), which runs as **two distinct weeks**
— a "Contemporary" week and a "Classic" week — with their own dates, faculty,
ages and disciplines. So we emit **one Offering per week**. We discover by
searching posts for "summer dance school" and keeping only those whose title
carries "summer dance school livorno" (this drops the old dateless Italian
"Summer School un mese" promo, post 332, and every competition). Editions are
year-stamped in the slug (post 9401 is the 2026 edition); kept per IDR-24.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-17):
  - The `solve=1` + JSON-viewer + CF-email-injection unwrap (`_unwrap`).
  - DATES off the two `<h4>` week headers ("from the 20 July until the 25 July
    2026" / "27 July until 1 August 2026") — English month map, year on the end.
  - The body detail is one flat paragraph stream under the last heading; we slice
    it on the in-body "Classic" week marker and **trim the shared tail** (the
    "Class location"/dress-code block) so the dress-code line "Socks for
    contemporary classes … pointe shoes for classical classes" can't leak a
    `contemporary` genre into the Classic offering — genres are matched per week.
  - GENRES: Contemporary → contemporary + repertoire; Classic → classical +
    pointe + repertoire.
  - AGES: Contemporary "14 years old and up" → 14+. Classic splits into two
    age-group Sessions ("11–13 years (Group 1); 14 years and up (Group 2)"),
    so one Offering with two Sessions (same week/fee, different age band).
  - TEACHERS: ALL-CAPS name lines (linked to `/services-aed-dance/` bio pages,
    or bare) each followed by a mixed-case role line; we filter discipline lines
    ("CONTEMPORARY TECHNIQUE …") out by stopword + shape, and keep name + role.
  - PRICE: €390 (three classes, one week); the €150 deposit / €240 balance are a
    payment split of that one fee (a note, not separate prices), and the €15
    A.E.D. membership is an association fee kept in the application note.
  - APPLICATION: status open ("APPLICATIONS ARE OPEN"); no fixed deadline
    ("until all available places are filled"); url = post link.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.fetch import PROXY_PARAMS_HEADER
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://aed.dance"
PROVIDER = "associazione-europea-danza"

ORG = Organization(name="Associazione Europea Danza", slug=PROVIDER, country="IT", city="Livorno")

_MONTHALT = parse.months_alt()
# "20 July until the 25 July 2026" / "27 July until 1 August 2026"
_DATES = re.compile(
    r"(\d{1,2})\s+("
    + _MONTHALT
    + r")\s+until\s+(?:the\s+)?(\d{1,2})\s+("
    + _MONTHALT
    + r")\s+(\d{4})",
    re.IGNORECASE,
)
_AGE_UP = re.compile(r"(\d{1,2})\s*years?\s*(?:old\s*)?and\s*up", re.IGNORECASE)
_AGE_RANGE = re.compile(r"(\d{1,2})\s*[–-]\s*(\d{1,2})\s*years", re.IGNORECASE)
# The course fee on the "three classes … one week" line reads either "390 euro"
# or "€390"; the €150 deposit / €240 balance sit elsewhere, so we read the fee
# off that line and prefer the euro-worded amount.
_FEE_EURO = re.compile(r"(\d[\d.,]*)\s*euro", re.IGNORECASE)
_FEE_SYM = re.compile(r"€\s*(\d[\d.,]*)")
_TIME = re.compile(r"\d{1,2}[:.,]\d{2}")

_GENRES: list[tuple[Genre, list[str]]] = [
    ("classical", ["classical"]),
    ("pointe", ["pointe", "punta"]),
    ("contemporary", ["contemporary"]),
    ("repertoire", ["repertoire", "repertory"]),
]

# A teacher name is an ALL-CAPS personal-name line; these tokens mark a line as a
# discipline / heading / button instead, so it isn't mistaken for a name.
_NOT_A_NAME = {
    "WEEK",
    "TECHNIQUE",
    "REPERTORY",
    "REPERTOIRE",
    "CONTEMPORARY",
    "CLASSICAL",
    "BALLET",
    "POINTE",
    "IMPROVISATION",
    "WORKSHOP",
    "APPLY",
    "NOW",
    "REGISTER",
    "DRESS",
    "CODE",
    "GROUP",
    "APPLICATIONS",
    "OPEN",
    "SCHEDULE",
    "FEES",
    "AGE",
}
_NAME_CHARS = re.compile(r"^[A-ZÀ-Þ][A-ZÀ-Þ' .\-]+$")


def scrape(client: httpx.Client) -> list[Offering]:
    posts = _fetch_json(
        client,
        f"{BASE}/wp-json/wp/v2/posts",
        params={
            "search": "summer dance school",
            "per_page": 20,
            "_fields": "id,title,link,content",
        },
    )
    return _build_offerings(posts, date.today())


def _fetch_json(client: httpx.Client, url: str, *, params: dict | None = None) -> list[dict]:
    resp = client.get(url, params=params, headers={PROXY_PARAMS_HEADER: "solve=1"})
    resp.raise_for_status()
    return _unwrap(resp.text)


def _unwrap(body: str) -> list[dict]:
    """Recover the JSON the proxy returned inside Chromium's JSON viewer.

    The `solve=1` (FlareSolverr) tier renders the response, so the JSON sits
    HTML-escaped inside `<pre>` and Cloudflare's email-protection script has
    injected *real* `<a class="__cf_email__">` tags into displayed emails. Since
    every legitimate angle-bracket in the JSON is escaped (`&lt;`/`&gt;`), the
    only real `<…>` tags left are those injections — strip them, then convert the
    structural entities back and parse.
    """
    match = re.search(r"<pre[^>]*>(.*)</pre>", body, re.DOTALL)
    inner = match.group(1) if match else body
    inner = re.sub(r"<[^>]*>", "", inner)
    inner = (
        inner.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#160;", " ")
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
    )
    data = json.loads(inner)
    return data if isinstance(data, list) else [data]


def _lines(content: wp.Content) -> list[str]:
    out: list[str] = []
    for section in content.sections:
        for node in section.nodes:
            for raw in wp.node_lines(node):
                cleaned = parse.clean(raw)
                if cleaned:
                    out.append(cleaned)
    return out


def _first(lines: list[str], *needles: str, start: int = 0) -> int | None:
    low = [n.lower() for n in needles]
    for i in range(start, len(lines)):
        text = lines[i].lower()
        if all(n in text for n in low):
            return i
    return None


def _dates(heading: str) -> tuple[date, date] | None:
    match = _DATES.search(heading)
    if not match:
        return None
    d1, m1, d2, m2, year = match.groups()
    y = int(year)
    return (
        date(y, parse.MONTHS[m1.lower()], int(d1)),
        date(y, parse.MONTHS[m2.lower()], int(d2)),
    )


def _genres(block: list[str]) -> list[Genre]:
    return parse.match_genres("\n".join(block), _GENRES)


def _price(block: list[str]) -> list[Price]:
    line = next((ln for ln in block if "three classes" in ln.lower()), "")
    match = _FEE_EURO.search(line) or _FEE_SYM.search(line)
    amount = parse.parse_amount(match.group(1)) if match else None
    if amount is None:
        return []
    return [
        Price(
            amount=amount,
            currency="EUR",
            label="Three classes, one week",
            includes=["tuition"],
            notes="€150 deposit at booking; €240 balance on the first day. "
            "A.E.D. membership (€15/year) is mandatory.",
        )
    ]


def _teachers(block: list[str]) -> list[Teacher]:
    out: list[Teacher] = []
    seen: set[str] = set()
    for i, line in enumerate(block):
        if not _is_name(line):
            continue
        role = block[i + 1] if i + 1 < len(block) else ""
        # The role line is mixed-case prose; a following ALL-CAPS line is a
        # discipline heading, not this teacher's role.
        role = role if role and not _is_name(role) and not role.isupper() else ""
        name = _titlecase(line)
        if name in seen:
            continue
        seen.add(name)
        role = re.sub(r"\s+([,.])", r"\1", parse.clean(role)).strip(" ,")
        out.append(Teacher(name=name, role=role or None))
    return out


def _is_name(line: str) -> bool:
    if not _NAME_CHARS.match(line):
        return False
    words = line.split()
    return 2 <= len(words) <= 4 and not any(w.strip(".'-") in _NOT_A_NAME for w in words)


def _titlecase(name: str) -> str:
    titled = name.title()
    return re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), titled)


def _timetable(block: list[str]) -> str | None:
    """Daily class times in a block — lines that open with an HH:MM time."""
    times = [ln for ln in block if _TIME.match(ln)]
    return "; ".join(times) or None


def _classic_sessions(block: list[str], start: date, end: date) -> list[Session]:
    """The Classic week's two age-group Sessions ("Group 1" / "Group 2")."""
    age_line = next((ln for ln in block if _AGE_RANGE.search(ln) or _AGE_UP.search(ln)), "")
    sessions: list[Session] = []
    for part in re.split(r"[;]", age_line):
        label = re.search(r"\((Group\s*\d)\)", part, re.IGNORECASE)
        age = _age(part)
        if not label or age is None:
            continue
        group = parse.clean(label.group(1)).title()
        times = _group_timetable(block, group)
        sessions.append(Session(label=group, start=start, end=end, ageRange=age, notes=times))
    return sessions


def _group_timetable(block: list[str], group: str) -> str | None:
    """The class times listed under a "Group N" sub-header in the Schedule block."""
    try:
        idx = next(i for i, ln in enumerate(block) if ln.strip().lower() == group.lower())
    except StopIteration:
        return None
    times: list[str] = []
    for ln in block[idx + 1 :]:
        if _TIME.match(ln):
            times.append(ln)
        elif ln.lower().startswith("group"):
            break
    return "; ".join(times) or None


def _age(text: str) -> dict | None:
    if m := _AGE_RANGE.search(text):
        return {"min": int(m.group(1)), "max": int(m.group(2))}
    if m := _AGE_UP.search(text):
        return {"min": int(m.group(1)), "max": None}
    return None


def _build_offerings(posts: list[dict], today: date) -> list[Offering]:
    offerings: list[Offering] = []
    for post in posts:
        title = html.unescape(post["title"]["rendered"])
        if "summer dance school livorno" not in title.lower():
            continue
        content = wp.parse(post["content"]["rendered"])
        headings = [s.heading for s in content.sections]
        lines = _lines(content)
        contemp_heading = next((h for h in headings if "contemporary" in h.lower()), "")
        classic_heading = next((h for h in headings if "classic" in h.lower()), "")

        i_contemp = _first(lines, "contemporary week")
        i_classic = _first(lines, "classic", "week from")
        i_tail = _first(lines, "class location") if i_classic is not None else None

        if c := _contemporary(post, contemp_heading, lines, i_contemp, i_classic):
            offerings.append(c)
        if k := _classic(post, classic_heading, lines, i_classic, i_tail):
            offerings.append(k)
    offerings.sort(key=lambda o: o.id)
    return offerings


def _source(post: dict) -> Source:
    return Source(provider=PROVIDER, url=post["link"], scrapedAt=now_utc())


def _location() -> Location:
    return Location(venue="Via Masi 7", city="Livorno", country="IT")


def _application(post: dict) -> Application:
    return Application(
        status="open",
        url=post["link"],
        notes="Open to students who regularly study dance (no beginners). "
        "A.E.D. membership (€15/year) mandatory. "
        "Applications accepted until all available places are filled.",
    )


def _contemporary(
    post: dict, heading: str, lines: list[str], i_start: int | None, i_end: int | None
) -> Offering | None:
    span = _dates(heading)
    if span is None or i_start is None:
        return None
    start, end = span
    block = lines[i_start : i_end if i_end is not None else len(lines)]
    return Offering(
        id=f"{PROVIDER}/{start.year}-contemporary",
        source=_source(post),
        title=f"Summer Dance School Livorno — Contemporary Week {start.year}",
        genres=_genres(block),
        ageRange=_age(next((ln for ln in block if _AGE_UP.search(ln)), "")),
        organization=ORG,
        location=_location(),
        schedule=Schedule(
            season="summer", start=start, end=end, timezone="Europe/Rome", notes=_timetable(block)
        ),
        teachers=_teachers(block),
        prices=_price(block),
        application=_application(post),
    )


def _classic(
    post: dict, heading: str, lines: list[str], i_start: int | None, i_end: int | None
) -> Offering | None:
    span = _dates(heading)
    if span is None or i_start is None:
        return None
    start, end = span
    block = lines[i_start : i_end if i_end is not None else len(lines)]
    sessions = _classic_sessions(block, start, end)
    age = (
        {"min": min(s.age_range["min"] for s in sessions if s.age_range), "max": None}
        if sessions
        else None
    )
    return Offering(
        id=f"{PROVIDER}/{start.year}-classic",
        source=_source(post),
        title=f"Summer Dance School Livorno — Classic Week {start.year}",
        genres=_genres(block),
        ageRange=age,
        organization=ORG,
        location=_location(),
        schedule=Schedule(
            season="summer", start=start, end=end, timezone="Europe/Rome", sessions=sessions
        ),
        teachers=_teachers(block),
        prices=_price(block),
        application=_application(post),
    )
