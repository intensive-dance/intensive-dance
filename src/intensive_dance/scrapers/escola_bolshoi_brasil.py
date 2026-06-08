"""Escola do Teatro Bolshoi no Brasil — short-term student courses, Joinville (BR).

The Bolshoi Theatre Ballet School's only branch outside Russia. Alongside its
free full-time vocational programme (out of scope — that's the long-term
*Ausbildung*, not an intensive), it sells dated, public, paid **short courses**
that any external dancer can register for: Cursos de Inverno (July, austral
winter), Vivências (a week "living" the school's routine), and one-off Workshops.
We emit one Offering per dated course.

API FIRST
No JSON API. `/wp-json/` returns the home HTML (not a WP REST root), there is no
`__NEXT_DATA__`/ld+json `Event` blob and no iCal feed — the site is a plain
server-rendered custom PHP app (Solidés "Minha Sapatilha" booking). A direct
httpx fetch with our UA returns the full markup, so no proxy is needed. We parse
HTML structurally off the clean `audicao-inscricao-meta` label/value block.

DISCOVERY
The course catalogue is split across `?tipo=` tabs and the bare `/cursos`
default only shows the current Inverno cohort, so we fetch `/cursos` plus every
known tab (`inverno`/`verao`/`workshop`/`vivencias`/…) and **union** the course
links (the tabs overlap heavily — most just echo the Inverno set — so we dedupe
by the numeric course id). Each card links one `/curso/<id>/<slug>` detail page =
one dated edition; we build one Offering per course. The numeric id is the
booking PK but the URL slug is the stable, human-readable offering id.

SCOPE
We keep **student-facing** short courses and skip the teacher-training ones
("Curso para Professores" / "Vivência para Professores", e.g. the Método Vaganova
modules) — those are continuing-ed for teachers, not student intensives.

LANGUAGE NOTE (Portuguese source)
Parsed language-agnostically wherever possible: numeric dates (DD/MM/YYYY), the
`R$` (BRL) price, numeric ages from the `Idade` field, gender enum from `Sexo`,
and genres/levels keyed off the course title. The committed title is the source's
own (Portuguese) course name, quoted faithfully; we don't machine-translate.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-08)
- MULTI-PAGE: one index fetch → per-course fetches (~14 in-scope editions, 2026).
- PER-COURSE LOCATION: most run in Joinville/SC, but the Belém/PA pop-up
  workshops (816/817) prove location must be read per course, not hardcoded.
- AGE RANGE: `Idade` "11–14" → bounded; the "N–100" sentinel (100 = open) →
  null max (e.g. the open "a partir de 14 anos" adult/advanced courses).
- GENDER on Session: Sexo Feminino/Masculino/Ambos → female/male/both.
- PRICES in BRL (`R$ 1.390,00`); R$ 0,00 free workshops carry no Price.
- APPLICATION status: "Não há mais vagas" (sold out) → closed; else open. These
  are open-enrollment paid courses with no audition → requirements = NoneReq.
- TEACHERS from the `Professores` meta, falling back to the "Professor(a):" line
  in the description (some courses leave the meta blank, e.g. 783). No per-course
  affiliations are published, so teachers carry a name only.
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from intensive_dance import parse
from intensive_dance.models import (
    Application,
    Gender,
    Genre,
    Level,
    Location,
    NoneReq,
    Offering,
    Organization,
    Price,
    Schedule,
    Session,
    Source,
    Teacher,
    now_utc,
)

BASE = "https://escolabolshoi.com.br"
INDEX_URL = f"{BASE}/cursos"
# The catalogue is split across these tabs; the bare /cursos only shows the
# current cohort, so we crawl them all and dedupe. Unknown/empty tabs are
# harmless (they just contribute no new ids).
_TIPOS = ("inverno", "verao", "workshop", "vivencias", "certificacao-especial", "bolshoi-online")
_INDEX_URLS = (INDEX_URL, *(f"{INDEX_URL}?page=cursos&tipo={t}" for t in _TIPOS))

ORG = Organization(
    name="Escola do Teatro Bolshoi no Brasil",
    slug="escola-bolshoi-brasil",
    country="BR",
    city="Joinville",
)

# Course-card link: /curso/<id>/<slug>
_CARD_RE = re.compile(r'href="(/curso/(\d+)/([a-z0-9][a-z0-9-]*))"')

# Teacher-training courses we skip (continuing-ed for teachers, not students).
_TEACHER_COURSE = re.compile(r"para\s+professores", re.IGNORECASE)

# Sentinel upper age the booking form uses for "open-ended" — not a real cap.
_OPEN_AGE_MAX = 100


def scrape(client: httpx.Client) -> list[Offering]:
    index_pages: list[str] = []
    for url in _INDEX_URLS:
        resp = client.get(url)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        index_pages.append(resp.text)
    paths = _course_paths(index_pages)

    offerings: list[Offering] = []
    for path in paths:
        page = client.get(urljoin(BASE, path))
        if page.status_code == 404:
            continue
        page.raise_for_status()
        offering = _build_offering(page.text, urljoin(BASE, path))
        if offering is not None:
            offerings.append(offering)

    offerings.sort(key=lambda o: (o.schedule.start or date.min, o.id))
    return offerings


def _course_paths(index_pages: list[str]) -> list[str]:
    """Distinct `/curso/<id>/<slug>` paths across all catalogue pages, by id.

    The `?tipo=` tabs overlap (most echo the default Inverno cohort), so the
    union is deduped on the numeric course id — the booking PK.
    """
    seen: dict[str, str] = {}
    for html in index_pages:
        for m in _CARD_RE.finditer(html):
            seen.setdefault(m.group(2), m.group(1))
    return [seen[cid] for cid in sorted(seen, key=int)]


# --- structured meta block: <span ..__label>Label</span><span ..__val>Value</span>


def _meta(tree: HTMLParser, label: str) -> str | None:
    for node in tree.css("div.audicao-inscricao-meta"):
        label_node = node.css_first("span.audicao-inscricao-meta__label")
        val_node = node.css_first("span.audicao-inscricao-meta__val")
        if label_node is None or val_node is None:
            continue
        if parse.clean(label_node.text()).lower() == label.lower():
            return parse.clean(val_node.text())
    return None


# --- dates: "Período do curso" → "21/07/2026 a 24/07/2026" (DD/MM/YYYY) ---------

_DATE_RANGE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*a\s*(\d{2})/(\d{2})/(\d{4})")


def _date_range(period: str | None) -> tuple[date | None, date | None]:
    if not period:
        return None, None
    m = _DATE_RANGE.search(period)
    if not m:
        return None, None
    d1, m1, y1, d2, m2, y2 = (int(g) for g in m.groups())
    return date(y1, m1, d1), date(y2, m2, d2)


# --- age: "Idade" → "11–14" / "14–100" (100 = open-ended sentinel) --------------

_AGE_RE = re.compile(r"(\d{1,3})\s*[–\-]\s*(\d{1,3})")


def _age_range(idade: str | None) -> dict | None:
    if not idade:
        return None
    m = _AGE_RE.search(idade)
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2))
    if hi >= _OPEN_AGE_MAX:
        return {"min": lo, "max": None}
    return {"min": lo, "max": hi}


# --- gender: "Sexo" → Feminino / Masculino / Ambos os sexos ---------------------


def _gender(sexo: str | None) -> Gender:
    low = (sexo or "").lower()
    if "femin" in low:
        return "female"
    if "mascul" in low:
        return "male"
    return "both"


# --- price: "Valor da inscrição R$ 1.390,00" (BRL; R$ 0,00 = free, no Price) -----

_PRICE_RE = re.compile(r"R\$\s*([\d.,]+)")


def _prices(tree: HTMLParser) -> list[Price]:
    val = _meta(tree, "Valor da inscrição")
    if val is None:
        # Fallback: the headline "Valor R$ …" inside the description block.
        node = tree.css_first("span.audicao-inscricao-meta__val")
        val = parse.clean(node.text()) if node else ""
    m = _PRICE_RE.search(val or "")
    if not m:
        return []
    amount = parse.parse_amount(m.group(1))
    if amount is None or amount <= 0:
        return []
    return [Price(amount=amount, currency="BRL", label="Registration fee", includes=["tuition"])]


# --- location: "Cidade / UF" → "Joinville / SC"; "Local" → venue ----------------


def _location(tree: HTMLParser) -> Location:
    venue = _meta(tree, "Local")
    city_uf = _meta(tree, "Cidade / UF") or ""
    city = parse.clean(city_uf.split("/")[0]) if "/" in city_uf else (city_uf or None)
    return Location(venue=venue or None, city=city or None, country="BR")


# --- genres / levels from the course title --------------------------------------

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("contemporary", ("contempor",)),
    ("repertoire", ("repertório", "repertorio", "variaç", "variac", "gala")),
    ("classical", ("clássico", "classico", "ballet", "vaganova", "vivência", "vivencia")),
    ("pointe", ("ponta",)),
]


def _genres(title: str) -> list[Genre]:
    found: list[Genre] = parse.match_genres(title, _GENRE_KEYWORDS)
    # Repertory variations / galas are danced on the classical syllabus → keep
    # classical alongside them. A purely contemporary course is not "classical".
    if "repertoire" in found and "classical" not in found:
        found.insert(0, "classical")
    if "contemporary" in found:
        found = [g for g in found if g != "classical"]
    return found or ["classical"]


_LEVEL_KEYWORDS: list[tuple[Level, tuple[str, ...]]] = [
    ("beginner", ("iniciante", "básico", "basico")),
    ("intermediate", ("intermediário", "intermediario")),
    ("advanced", ("avançado", "avancado")),
]


def _levels(title: str) -> list[Level]:
    low = title.lower()
    levels = [lvl for lvl, keys in _LEVEL_KEYWORDS if any(k in low for k in keys)]
    if "adulto" in low and "open" not in levels:
        levels.append("open")
    return levels


# --- teachers: "Professores" meta, else the "Professor(a):" description line -----
# The description block separates fields with <br>/<b> tags, e.g.
# "<b>Professor: Maikon Golini<br></b><b>Horário:</b> …", so we turn tags into a
# delimiter before matching — otherwise .text() glues the name onto "Horário".

_DESC_TEACHER_RE = re.compile(r"Professor(?:a|es)?\s*:\s*([^|]+)", re.IGNORECASE)


def _teacher_name(tree: HTMLParser) -> str | None:
    name = _meta(tree, "Professores")
    if name:
        return name
    desc = tree.css_first("div.curso-descr-content")
    if desc is None or desc.html is None:
        return None
    text = parse.clean(re.sub(r"(?i)<br\s*/?>|</?b>|</?p>", "|", desc.html))
    text = re.sub(r"<[^>]+>", "", text)
    m = _DESC_TEACHER_RE.search(text)
    return parse.clean(m.group(1)) if m and parse.clean(m.group(1)) else None


def _teachers(tree: HTMLParser) -> list[Teacher]:
    name = _teacher_name(tree)
    return [Teacher(name=name)] if name else []


# --- builder --------------------------------------------------------------------


def _offering_slug(url: str) -> str:
    m = re.search(r"/curso/\d+/([a-z0-9][a-z0-9-]*)", url)
    return m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]


def _is_sold_out(html: str) -> bool:
    return "não há mais vagas" in html.lower()


def _build_offering(html: str, url: str) -> Offering | None:
    tree = HTMLParser(html)

    h1 = tree.css_first("h1")
    title = parse.clean(h1.text()) if h1 else ""
    if not title or _TEACHER_COURSE.search(title):
        return None  # teacher-training course → out of student scope

    start, end = _date_range(_meta(tree, "Período do curso"))
    if start is None:
        return None  # undated — discovery anchor missing

    season = str(start.year)
    age_range = _age_range(_meta(tree, "Idade"))
    gender = _gender(_meta(tree, "Sexo"))
    period_note = _meta(tree, "Período do curso")
    sold_out = _is_sold_out(html)

    return Offering(
        id=f"escola-bolshoi-brasil/{_offering_slug(url)}",
        source=Source(provider="escola-bolshoi-brasil", url=url, scrapedAt=now_utc()),
        title=title,
        genres=_genres(title),
        level=_levels(title),
        ageRange=age_range,
        organization=ORG,
        location=_location(tree),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="America/Sao_Paulo",
            sessions=[
                Session(
                    label=title,
                    start=start,
                    end=end,
                    ageRange=age_range,
                    gender=gender,
                    notes=period_note,
                )
            ],
            notes=period_note,
        ),
        teachers=_teachers(tree),
        prices=_prices(tree),
        application=Application(
            status="closed" if sold_out else "open",
            url=url,
            requirements=[NoneReq()],
            notes="Não há mais vagas para este curso." if sold_out else None,
        ),
    )
