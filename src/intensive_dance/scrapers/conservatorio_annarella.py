"""Conservatório Internacional de Ballet e Dança Annarella (PT) — Leiria.

API FIRST
The site is WordPress, served from the `/site/` subfolder: `GET
https://conservatorioannarella.com/site/wp-json/wp/v2/pages?slug=<slug>` returns
each course page's full body in `content.rendered` (clean prose + lists, no page
builder that drops the body — unlike ABT / Balletto di Roma). No HTML scrape, no
proxy, no JS render needed. No `ld+json` is present.

DISCOVERY — the school is vocational but runs public, dated, open-enrollment
short courses with their own pages, linked from `/site/cursos/`. One Offering per
dated edition that has a real detail page:
  1. CURSO INTENSIVO DE VERÃO — `/site/curso-intensivo-de-verao/`
     2026 edition, five selectable one-week blocks (29 Jun – 31 Jul 2026), ages
     8–20, one Offering with one Session per week.
  2. CURSO INTENSIVO DE INVERNO — `/site/curso-intensivo-de-inverno/`
     The page still carries the 2025 edition (6–11 Jan 2025); kept per IDR-24
     (ended cycles stay in the store, "past" is derived consumer-side), ages 8+.
We deliberately do NOT emit:
  - CURSO DE PÁSCOA — its page (`/site/curso-de-pascoa/`) is a bare registration
    form; the date ("6–10 abril 2026") lives only on the index and the page
    states no genres/ages/requirements, so an Offering would be a genre-less stub.
  - CURSO DE NATAL / teacher-training "Cursos de Professores" — "datas por
    definir" (no dated edition) and teacher training (not a student intensive).

PRICES: every course states "Valores sob consulta" (on request) → `prices` is
left empty (not stated). The page also states accommodation / meals / transport
are the dancer's own responsibility (not included) — there is no fee to attach
that to, so it is recorded only in the application notes context, not invented.

REQUIREMENTS: a YouTube (unlisted) audition video with a specific list of
combinations (1st arabesque, à la seconde, adage, pirouette, petit/grand allegro,
plus a pointe combination for girls) → VideoReq(specific). Under-11s (winter:
≤12) and returning students are exempt — captured in `application.notes`, the
requirement itself stays.

GENRES: matched against the "modalidades" curriculum sentence only (not loose
prose — the school name itself contains "Ballet"). Ballet→classical,
Contemporâneo→contemporary, Carácter→character, Repertório→repertoire,
Pontas→pointe. Jazz / Danças Latinas / Pas de Deux / Preparação Física are not
genres in our enum and are dropped.

WHAT THIS SCRAPER EXERCISES (verified live 2026-06-11)
- WordPress REST `content.rendered` from a `/site/` subfolder install.
- Portuguese-language parsing: PT month map, ages, deadline, modalidades genres.
- One Offering with multiple Sessions (the summer weeks) vs. a single-span one.
- A kept ended cycle (winter 2025) alongside a current one (summer 2026).
- VideoReq(specific) with an exemption note; empty `prices` ("sob consulta").
- Open-ended age band (winter, null max) vs. closed band (summer 8–20).
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from intensive_dance import parse, wp
from intensive_dance.models import (
    Application,
    Genre,
    Location,
    Offering,
    Organization,
    Schedule,
    Session,
    Source,
    VideoReq,
    now_utc,
)

BASE = "https://conservatorioannarella.com/site"
SUMMER_SLUG = "curso-intensivo-de-verao"
WINTER_SLUG = "curso-intensivo-de-inverno"

ORG = Organization(
    name="Conservatório Internacional de Ballet e Dança Annarella",
    slug="conservatorio-annarella",
    country="PT",
    city="Leiria",
)
VENUE = "Conservatório Internacional de Ballet e Dança Annarella Sanchez"

_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
_MONTHALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_GENRE_KEYWORDS: list[tuple[Genre, tuple[str, ...]]] = [
    ("classical", ("ballet",)),
    ("contemporary", ("contempor",)),
    ("character", ("carácter", "caracter", "carater")),
    ("repertoire", ("repertóri", "repertori")),
    ("pointe", ("pontas", "pointe")),
]


def scrape(client: httpx.Client) -> list[Offering]:
    offerings = [
        _build_summer(_page(client, SUMMER_SLUG)),
        _build_winter(_page(client, WINTER_SLUG)),
    ]
    offerings.sort(key=lambda o: o.id)
    return offerings


def _page(client: httpx.Client, slug: str) -> str:
    record = wp.fetch_page(client, slug, base=BASE)
    if record is None:
        raise RuntimeError(f"Annarella page not found: {slug}")
    return wp.plain_text(record["content"]["rendered"])


# --- Curso Intensivo de Verão (summer) ----------------------------------------


def _build_summer(text: str) -> Offering:
    year = _year(text, r"ver[ãa]o\s*(20\d{2})")
    weeks = _summer_weeks(text, year)
    start = min((s for s, _ in weeks), default=None)
    end = max((e for _, e in weeks), default=None)
    return Offering(
        id=f"conservatorio-annarella/curso-intensivo-de-verao-{year}",
        source=Source(
            provider="conservatorio-annarella", url=f"{BASE}/{SUMMER_SLUG}/", scrapedAt=now_utc()
        ),
        title=f"Curso Intensivo de Verão {year}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Leiria", country="PT"),
        schedule=Schedule(
            season=str(year),
            start=start,
            end=end,
            timezone="Europe/Lisbon",
            sessions=[Session(label=_week_label(s, e), start=s, end=e) for s, e in weeks],
            notes=_semanas_notes(text),
        ),
        prices=[],
        application=_application(text, f"{BASE}/{SUMMER_SLUG}/"),
    )


# Each week is "29 junho - 3 julho" (cross-month) or "20 - 24 julho" (the start
# day inherits the end month). The year is carried by the page title, not the
# SEMANAS line, so it is threaded in.
_WEEK = re.compile(
    r"(\d{1,2})(?:\s+(" + _MONTHALT + r"))?\s*[-–]\s*(\d{1,2})\s+(" + _MONTHALT + r")",
    re.IGNORECASE,
)


def _summer_weeks(text: str, year: int) -> list[tuple[date, date]]:
    region = _semanas_notes(text) or text
    weeks: list[tuple[date, date]] = []
    for d1, mon1, d2, mon2 in _WEEK.findall(region):
        end_m = _MONTHS[mon2.lower()]
        start_m = _MONTHS[mon1.lower()] if mon1 else end_m
        weeks.append((date(year, start_m, int(d1)), date(year, end_m, int(d2))))
    return weeks


_SEMANAS = re.compile(
    r"SEMANAS?\s*:?(.*?)(?:\d+\s*[ªº]\s*Gala|Gala|Valores|\bO Curso|\bJá est)",
    re.IGNORECASE | re.DOTALL,
)


def _semanas_notes(text: str) -> str | None:
    m = _SEMANAS.search(text)
    return parse.clean(m.group(1)) if m else None


def _week_label(start: date, end: date) -> str:
    return f"{start.isoformat()} – {end.isoformat()}"


# --- Curso Intensivo de Inverno (winter) --------------------------------------

# "6 - 11 de janeiro de 2025": a single day range with an explicit trailing year.
_WINTER_RANGE = re.compile(
    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+de\s+(" + _MONTHALT + r")\s+de\s+(\d{4})",
    re.IGNORECASE,
)


def _build_winter(text: str) -> Offering:
    m = _WINTER_RANGE.search(text)
    if m:
        d1, d2, month, yr = m.groups()
        year = int(yr)
        mon = _MONTHS[month.lower()]
        start: date | None = date(year, mon, int(d1))
        end: date | None = date(year, mon, int(d2))
    else:
        year = _year(text, r"inverno\s*(20\d{2})")
        start = end = None
    return Offering(
        id=f"conservatorio-annarella/curso-intensivo-de-inverno-{year}",
        source=Source(
            provider="conservatorio-annarella", url=f"{BASE}/{WINTER_SLUG}/", scrapedAt=now_utc()
        ),
        title=f"Curso Intensivo de Inverno {year}",
        genres=_genres(text),
        ageRange=_age_range(text),
        organization=ORG,
        location=Location(venue=VENUE, city="Leiria", country="PT"),
        schedule=Schedule(
            season=str(year),
            start=start,
            end=end,
            timezone="Europe/Lisbon",
            notes=m.group(0) if m else None,
        ),
        prices=[],
        application=_application(text, f"{BASE}/{WINTER_SLUG}/"),
    )


# --- shared helpers -----------------------------------------------------------


def _year(text: str, pattern: str) -> int:
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    fallback = re.search(r"\b(20\d{2})\b", text)
    return int(fallback.group(1)) if fallback else date.today().year


_MODALIDADES = re.compile(r"modalidades[^:]*:(.*?)entre outras", re.IGNORECASE | re.DOTALL)


def _genres(text: str) -> list[Genre]:
    m = _MODALIDADES.search(text)
    curriculum = m.group(1) if m else text
    return parse.match_genres(curriculum, _GENRE_KEYWORDS, default=["classical"])


# Closed "desde os 8 anos até aos 20 anos"; open "maiores de 8 anos" (null max).
_AGE_CLOSED = re.compile(
    r"desde\s+os\s+(\d{1,2})\s+anos\s+at[ée]\s+aos\s+(\d{1,2})\s+anos", re.IGNORECASE
)
_AGE_OPEN = re.compile(r"maiores\s+de\s+(\d{1,2})\s+anos", re.IGNORECASE)


def _age_range(text: str) -> dict | None:
    closed = _AGE_CLOSED.search(text)
    if closed:
        return {"min": int(closed.group(1)), "max": int(closed.group(2))}
    open_ = _AGE_OPEN.search(text)
    if open_:
        return {"min": int(open_.group(1)), "max": None}
    return None


_VIDEO_MARKER = re.compile(
    r"Requisitos\s+para\s+o\s+v[íi]deo\s*:(.*?)(?:O\s+v[íi]deo|2\.)", re.IGNORECASE | re.DOTALL
)
_DEADLINE = re.compile(
    r"Data\s+limite\s+para\s+submiss[ãa]o.*?(\d{1,2})\s+de\s+(" + _MONTHALT + r")\s+de\s+(\d{4})",
    re.IGNORECASE | re.DOTALL,
)
_EXEMPTION = re.compile(r"(NOTA\s*:?\s*os\s+alunos.*?inscri[çc][ãa]o\.)", re.IGNORECASE | re.DOTALL)


def _application(text: str, url: str) -> Application:
    requirements = []
    marker = _VIDEO_MARKER.search(text)
    if marker:
        requirements.append(
            VideoReq(specificity="specific", description=parse.clean(marker.group(1)))
        )
    deadline = None
    dm = _DEADLINE.search(text)
    if dm:
        day, month, yr = dm.groups()
        deadline = date(int(yr), _MONTHS[month.lower()], int(day))
    exemption = _EXEMPTION.search(text)
    return Application(
        url=url,
        requirements=requirements,
        deadline=deadline,
        notes=parse.clean(exemption.group(1)) if exemption else None,
    )
