"""Unit tests for the CORDS. Dance (Wrocław) summer-intensive scraper.

CORDS is a WordPress/Elementor site whose page body is present in
`content.rendered`; these tests pin the parsing judgement calls a hash check
can't catch — Polish-date span parsing, the class-pass price ladder, the
edition-selection (latest year, bare slug over its `-N` republish, year-less
2023 page via title), and the marquee teacher → affiliation mapping resolved
from the /team/ page. Inline HTML/JSON snippets, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import cords_dance as cd

# --- a minimal but representative edition page body --------------------------

EDITION_HTML = """
<div class="elementor-widget-container">
  <p>Wrocław ul. Braniborska 59 | 21 -26 lipca 2025</p>
</div>
<h2>INTENSYWNE WARSZTATY BALETOWE 2025</h2>
<p>Ballet Beginner/Intermediate, Ballet Advanced, 4 Pointe, Neoclassical
Choreography, Variation I and II, Contemporary, Pointe Work, Floor Barre.</p>
<h3>Nauczyciele</h3>
<h4>Marta Kulikowska de Nałęcz</h4><a>Zobacz</a>
<h4>SHANNON MAYNOR</h4><a>Zobacz</a>
<h4>Anna Kowalska (Mendakiewicz)</h4><a>Zobacz</a>
<h4>Beata Nawrot</h4><a>Zobacz</a>
<h3>Grafik</h3>
<table><tr><td>MONDAY 21.07</td></tr></table>
<h3>Cennik</h3>
<p>EARLY BIRDS I – 15% do 13 czerwca EARLY BIRDS II – 10% do 27 czerwca</p>
<p>Zapisy prowadzimy do 15 LIPCA !</p>
<ul>
  <li><span>1 - 90 PLN</span></li>
  <li><span>6 - 500 PLN</span></li>
  <li><span>40 - 2400 PLN</span></li>
</ul>
<h3>Golden Pass</h3><span>(obejmuje wejście na wszystkie lekcje)</span><span>3000 PLN</span>
"""

TEAM_HTML = """
<h4>Marta Kulikowska de Nałęcz</h4>
<p>Dancer, pedagogue, choreographer. She has worked as a soloist at the Wrocław
Opera. She currently works as an artistic director at Split Dance School.</p>
<h4>SHANNON MAYNOR</h4>
<p>originally from California, trained and performed with San Francisco Ballet
before joining Oregon Ballet Theatre.</p>
<h4>Anna Kowalska (Mendakiewicz)</h4>
<p>Graduate of the John Cranko Schule. She started her professional life at the
Vienna State Opera and later danced at the Boris Eifman theatre.</p>
<h4>Beata Nawrot</h4>
<p>Dancer, trainer, instructor. Author of the Train Like Dancers programme.</p>
"""


def _page(slug, title, content, status="publish"):
    return {
        "id": 1,
        "slug": slug,
        "status": status,
        "link": f"https://cordsdance.com/{slug}/",
        "title": {"rendered": title},
        "content": {"rendered": content},
    }


# --- dates --------------------------------------------------------------------


def test_dates_polish_span():
    start, end, year = cd._dates("Wrocław | 21 -26 lipca 2025")
    assert (start, end, year) == (date(2025, 7, 21), date(2025, 7, 26), 2025)


def test_dates_other_polish_month():
    start, end, year = cd._dates("warsztaty 3 - 8 sierpnia 2024")
    assert (start, end, year) == (date(2024, 8, 3), date(2024, 8, 8), 2024)


def test_dates_none_when_absent():
    assert cd._dates("no date here") == (None, None, None)


def test_deadline_takes_latest_of_several():
    text = "15% do 13 czerwca, 10% do 27 czerwca, zapisy do 15 lipca"
    assert cd._deadline(text, 2025) == date(2025, 7, 15)


def test_deadline_none_without_year():
    assert cd._deadline("do 15 lipca", None) is None


# --- genres -------------------------------------------------------------------


def test_genres_from_class_menu():
    text = "Ballet Advanced, 4 Pointe, Neoclassical Choreography, Variation I, Contemporary"
    assert cd._genres(text) == ["classical", "contemporary", "neoclassical", "pointe", "repertoire"]


def test_genres_default_classical():
    assert cd._genres("a ballet studio in Wrocław") == ["classical"]


# --- prices -------------------------------------------------------------------


def test_prices_pass_ladder_and_golden():
    prices = cd._prices("1 - 90 PLN 6 - 500 PLN 40 - 2400 PLN Golden Pass (…) 3000 PLN")
    by_label = {p.label: p for p in prices}
    assert by_label["1-class pass"].amount == 90.0
    assert by_label["40-class pass"].amount == 2400.0
    golden = by_label["Golden Pass (all classes)"]
    assert golden.amount == 3000.0
    assert golden.currency == "PLN"
    assert all(p.includes == ["tuition"] for p in prices)


# --- edition selection --------------------------------------------------------


def test_latest_edition_prefers_recent_year():
    pages = [
        _page("summer-intensive", "Summer intensive 2023", "x"),
        _page("summer-intensive-2024", "Summer intensive 2024", "x"),
        _page("summer-intensive-2025", "Summer intensive 2025", "x"),
    ]
    chosen = cd._latest_edition(pages)
    assert chosen is not None and chosen["slug"] == "summer-intensive-2025"


def test_latest_edition_bare_slug_beats_republish():
    # the bare 2025 slug must win over its -2 republish (NOT treated as a dup year)
    pages = [
        _page("summer-intensive-2025-2", "Summer intensive 2025", "dup-body"),
        _page("summer-intensive-2025", "Summer intensive 2025", "canonical-body"),
    ]
    chosen = cd._latest_edition(pages)
    assert chosen is not None and chosen["slug"] == "summer-intensive-2025"


def test_latest_edition_year_from_title_for_yearless_slug():
    pages = [_page("summer-intensive", "Summer intensive 2023", "x")]
    chosen = cd._latest_edition(pages)
    assert chosen is not None and chosen["slug"] == "summer-intensive"


def test_latest_edition_ignores_drafts_and_none():
    assert cd._latest_edition([]) is None
    pages = [_page("summer-intensive-2025", "Summer intensive 2025", "x", status="draft")]
    assert cd._latest_edition(pages) is None


# --- teachers + affiliations --------------------------------------------------


def test_featured_names_between_nauczyciele_and_grafik():
    names = cd._featured_names(EDITION_HTML)
    assert names == [
        "Marta Kulikowska de Nałęcz",
        "SHANNON MAYNOR",
        "Anna Kowalska (Mendakiewicz)",
        "Beata Nawrot",
    ]


def test_teachers_resolve_affiliations_from_team_page():
    names = cd._featured_names(EDITION_HTML)
    teachers = cd._teachers(names, TEAM_HTML)
    by_name = {t.name: t for t in teachers}

    # all-caps roster name is title-cased
    assert "Shannon Maynor" in by_name
    sf = {a.organization for a in by_name["Shannon Maynor"].affiliations}
    assert "San Francisco Ballet" in sf and "Oregon Ballet Theatre" in sf

    anna = {a.organization for a in by_name["Anna Kowalska (Mendakiewicz)"].affiliations}
    assert {"John Cranko School", "Vienna State Opera", "Boris Eifman Ballet"} <= anna

    # a single named house carries a past/present flag
    marta = by_name["Marta Kulikowska de Nałęcz"].affiliations
    assert marta and marta[0].organization == "Opera Wrocławska"

    # a conditioning coach with no ballet-house bio gets no affiliations (not invented)
    assert by_name["Beata Nawrot"].affiliations == []


def test_tidy_name_keeps_parenthetical():
    assert cd._tidy_name("SHANNON MAYNOR") == "Shannon Maynor"
    assert cd._tidy_name("Anna Kowalska (Mendakiewicz)") == "Anna Kowalska (Mendakiewicz)"


# --- full build ---------------------------------------------------------------


def test_build_offerings_happy_path():
    pages = [
        _page("summer-intensive-2025", "Summer intensive 2025", EDITION_HTML),
        _page("team", "Team", TEAM_HTML),
    ]
    offerings = cd._build_offerings(pages, TEAM_HTML, date(2026, 6, 8))
    assert len(offerings) == 1
    o = offerings[0]

    assert o.id == "cords-dance/summer-intensive-2025"
    assert o.title == "CORDS. Dance Summer Intensive 2025"
    assert o.schedule.season == "2025"
    assert o.schedule.start == date(2025, 7, 21) and o.schedule.end == date(2025, 7, 26)
    assert o.schedule.timezone == "Europe/Warsaw"

    assert o.location is not None
    assert o.location.city == "Wrocław" and o.location.country == "PL"

    # open-enrolment: explicitly no audition
    assert [r.type for r in o.application.requirements] == ["none"]
    assert o.application.deadline == date(2025, 7, 15)
    assert o.application.url == cd.APPLY_URL

    assert {p.currency for p in o.prices} == {"PLN"}
    assert any(p.label == "Golden Pass (all classes)" for p in o.prices)
    assert len(o.teachers) == 4


def test_build_offerings_empty_when_no_edition():
    assert (
        cd._build_offerings([_page("team", "Team", TEAM_HTML)], TEAM_HTML, date(2026, 6, 8)) == []
    )
