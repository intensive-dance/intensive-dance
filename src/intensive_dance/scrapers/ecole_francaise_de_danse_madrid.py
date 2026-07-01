"""École Française de Danse Madrid — Summer intensives (Madrid, ES).

API FIRST: ecolefrancaisededanse.com is WordPress + **The Events Calendar**
(Tribe). The dated editions are exposed via the Tribe Events REST API
(`/wp-json/tribe/events/v1/events?start_date=…`) with clean start/end
dates, titles, and category tags — so no HTML needed for the booking
structure. Ages/level detail from the main course page (Spanish prose:
"Elemental 8–11", "Intermedio 10–14", "Avanzado 14+" and adult tracks).

DISCOVERY: the summer programme has two bookable tracks — **student**
intensives ("INTENSIVOS ESTUDIANTES") and **adult** intensives
("INTENSIVOS ADULTOS") — each running multiple weeks, plus a special
**masterclass** ("PROGRAMA ESPECIAL") led by Stéphane Phavorin. We emit
one Offering per track, with each bookable week as a `Session`:
  - **Student Intensive** — weeks 1 (29 Jun–3 Jul) and 3 (13–17 Jul);
    age bands from the course page: Elemental 8–11, Intermedio 10–14,
    Avanzado 14+. Level ranges per Session.
  - **Adult Intensive** — weeks 1 (29 Jun–3 Jul), 2 (6–10 Jul), and
    3 (13–17 Jul). Ages 18+.
  - **Phavorin Masterclass** — week 2 only (6–10 Jul), separate
    Offering because it's a curated special event, not the regular
    intensive track.

WHAT WE EXTRACT (verified live 2026-07-01):
  - DATES: from Tribe Events REST `start_date`/`end_date`.
  - TRACKS: adult (cat "INTENSIVOS ADULTOS"), student (cat "INTENSIVOS
    ESTUDIANTES"), Phavorin (cat "PROGRAMA ESPECIAL" + "INTENSIVOS
    ESTUDIANTES").
  - AGES: student/Phavorin: youngest band 8 (Elemental) → eldest 14
    (Avanzado is 14+, so upper is open). Adult: 18+.
  - GENRES: classical ballet + repertoire + contemporary (from the course
    page curriculum list: "Puntas, Saltos, Repertorio y Variaciones,
    Contemporáneo").
  - PRICES: none on the REST events (fees behind a form).
  - LOCATION: Madrid, ES.
  - APPLICATION: open (no audition stated for the weekly intensives).

WHAT THIS SCRAPER EXERCISES: Tribe Events REST API (API-first WP multi-edition
discovery); category-based track deduplication; one Offering per track with
per-week Sessions; Spanish age ranges from a course prose page; special-event
(Phavorin) as a standalone Offering; raise-on-degraded fetch.
"""

from __future__ import annotations

from datetime import date

import httpx

from intensive_dance.models import (
    Application,
    Genre,
    Level,
    Location,
    Offering,
    Organization,
    Schedule,
    Session,
    Source,
    now_utc,
)

BASE = "https://ecolefrancaisededanse.com"
EVENTS = f"{BASE}/wp-json/tribe/events/v1/events"
COURSE_PAGE = f"{BASE}/cursos-intensivos-verano-ballet-clasico-formacion-profesional/"

ORG = Organization(
    name="École Française de Danse Madrid",
    slug="ecole-francaise-de-danse-madrid",
    country="ES",
    city="Madrid",
)
VENUE = "École Française de Danse, Madrid"

_GENRES: list[Genre] = ["classical", "repertoire", "contemporary"]

# Category slug → our track key.
_CAT_TRACK = {
    "INTENSIVOS ADULTOS": "adult",
    "INTENSIVOS ESTUDIANTES": "student",
    "PROGRAMA ESPECIAL": "masterclass",
}


def scrape(client: httpx.Client) -> list[Offering]:
    events = _fetch_events(client)
    if not events:
        raise ValueError("EFD Madrid: no Tribe events returned (degraded fetch?)")
    return _build_offerings(events)


def _fetch_events(client: httpx.Client) -> list[dict]:
    """All published summer intensive events for 2026 via Tribe REST."""
    resp = client.get(EVENTS, params={"per_page": 50, "start_date": "2026-01-01"})
    resp.raise_for_status()
    data = resp.json()
    return data.get("events", [])


def _build_offerings(events: list[dict]) -> list[Offering]:
    # Group events by track.
    tracks: dict[str, list[dict]] = {"adult": [], "student": [], "masterclass": []}
    for ev in events:
        cat_names = {c["name"] for c in ev.get("categories", [])}
        # An event can carry multiple category slugs. Phavorin carries both
        # INTENSIVOS ESTUDIANTES and PROGRAMA ESPECIAL — masterclass takes priority.
        track = "masterclass" if "PROGRAMA ESPECIAL" in cat_names else None
        if track is None:
            for cat_name, tk in _CAT_TRACK.items():
                if cat_name in cat_names:
                    track = tk
                    break
        if track is None:
            continue  # unknown category — skip
        tracks[track].append(ev)

    offerings: list[Offering] = []
    for tk, evs in tracks.items():
        if not evs:
            continue
        offerings.append(_track_offering(tk, evs))
    return offerings


def _track_offering(track: str, events: list[dict]) -> Offering:
    sessions = sorted([_session(ev) for ev in events], key=lambda s: s.start or date.min)
    start = min((s.start for s in sessions if s.start), default=None)
    end = max((s.end for s in sessions if s.end), default=None)
    season = str(start.year) if start else "unknown"
    age = _age_range(track)
    slug = track if track != "masterclass" else "phavorin-masterclass"
    title = _TITLE.get(track, track.capitalize())
    level: list[Level] = ["open"] if track == "adult" else ["intermediate", "advanced"]

    return Offering(
        id=f"{ORG.slug}/{slug}-{season}",
        source=Source(provider=ORG.slug, url=COURSE_PAGE, scrapedAt=now_utc()),
        title=f"{title} {season}",
        genres=_GENRES,
        level=level,
        ageRange=age,
        organization=ORG,
        location=Location(city="Madrid", country="ES"),
        schedule=Schedule(
            season=season,
            start=start,
            end=end,
            timezone="Europe/Madrid",
            sessions=sessions,
        ),
        application=_application(track),
    )


_TITLE: dict[str, str] = {
    "student": "Intensivos de Verano",
    "adult": "Intensivos de Verano para Adultos",
    "masterclass": "Curso Intensivo con Stéphane Phavorin",
}


def _session(ev: dict) -> Session:
    start = _parse_date(ev.get("start_date"))
    end = _parse_date(ev.get("end_date"))
    notes = ev.get("title", "")
    return Session(label=notes, start=start, end=end)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except (ValueError, IndexError):
        return None


# Student ages: Elemental 8–11, Intermedio 10–14, Avanzado 14+. The youngest
# bound is 8 (Elemental); the upper bound is open (Avanzado is 14+, not capped).
# Adult: 18+.
# Phavorin: student-level masterclass, same age range as student track.
def _age_range(track: str) -> dict | None:
    if track == "adult":
        return {"min": 18}
    return {"min": 8}  # student / masterclass — open-topped


def _application(track: str) -> Application:
    url = (
        COURSE_PAGE
        if track != "masterclass"
        else f"{BASE}/evento/curso-intensivo-con-stephane-phavorin-ballet-master/"
    )
    return Application(url=url)
