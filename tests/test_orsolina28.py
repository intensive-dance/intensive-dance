"""Tests for the Orsolina28 scraper.

All tests are offline — no network. They feed inline HTML or page-file
fixtures captured from the live site on 2026-06-08.
"""

from __future__ import annotations

from datetime import date

import pytest
from selectolax.parser import HTMLParser

from intensive_dance.scrapers.orsolina28 import (
    _build_offering,
    _edition_slugs,
    _genres,
    _parse_dates,
    _parse_deadline,
    _tab_prices,
)

# ---------------------------------------------------------------------------
# _parse_dates
# ---------------------------------------------------------------------------

DATE_CASES = [
    ("June 14 – June 21, 2026", date(2026, 6, 14), date(2026, 6, 21)),
    ("July 5 – July 12, 2026", date(2026, 7, 5), date(2026, 7, 12)),
    ("August 9 – August 16, 2026", date(2026, 8, 9), date(2026, 8, 16)),
    # Cross-month
    ("June 28 – July 5, 2026", date(2026, 6, 28), date(2026, 7, 5)),
    # Year on first side too
    ("June 14, 2026 – June 21, 2026", date(2026, 6, 14), date(2026, 6, 21)),
]


@pytest.mark.parametrize("text,expected_start,expected_end", DATE_CASES)
def test_parse_dates(text: str, expected_start: date, expected_end: date) -> None:
    start, end = _parse_dates(text)
    assert start == expected_start
    assert end == expected_end


def test_parse_dates_no_year_returns_none() -> None:
    start, end = _parse_dates("June 14 – June 21")
    assert start is None
    assert end is None


def test_parse_dates_empty_returns_none() -> None:
    start, end = _parse_dates("")
    assert start is None
    assert end is None


# ---------------------------------------------------------------------------
# _parse_deadline
# ---------------------------------------------------------------------------

_DEADLINE_STANDARD = (
    "Deadlines February 4, 2026 at 6:00 P.M. (CET): Deadline for the submission "
    "of an application; March 3, 2026: Announcement of selected participants."
)

_DEADLINE_GAGALAB = (
    "COST Application fee: ILS 150 (non-refundable) Tuition Early Bird rate, "
    "until April 13: ILS 2340 In case of cancellation before April 22, 2026, "
    "a 90% refund will be issued;"
)


def test_parse_deadline_standard() -> None:
    result = _parse_deadline(_DEADLINE_STANDARD)
    assert result == date(2026, 2, 4)


def test_parse_deadline_gagalab_returns_none() -> None:
    """GagaLab tab text has no submission-deadline bullet → None."""
    result = _parse_deadline(_DEADLINE_GAGALAB)
    assert result is None


# ---------------------------------------------------------------------------
# _genres
# ---------------------------------------------------------------------------


def test_genres_contemporary_default() -> None:
    """Text with no keywords still yields contemporary (season default)."""
    genres = _genres("A program dedicated to the study of movement.")
    assert "contemporary" in genres


def test_genres_adds_repertoire_when_mentioned() -> None:
    genres = _genres(
        "participants will study and perform repertoire from the works of the choreographer"
    )
    assert "contemporary" in genres
    assert "repertoire" in genres


def test_genres_gaga_matches_contemporary() -> None:
    genres = _genres(
        "GagaLab: six days of intensive physical research based on Gaga movement language"
    )
    assert "contemporary" in genres


def test_genres_classical_from_ballet_class() -> None:
    genres = _genres(
        "Morning ballet classes alternating with improvisation-based awareness classes."
    )
    assert "contemporary" in genres
    assert "classical" in genres


# ---------------------------------------------------------------------------
# _tab_prices (via HTMLParser node)
# ---------------------------------------------------------------------------

_STANDARD_TAB_HTML = """
<div class="Tabs-content">
  <ul>
    <li>Application Fee: €40 (non-refundable)</li>
    <li>Tuition: € 1.500
      <ul>
        <li>Early Bird, by March 17, 2026: € 1.400</li>
      </ul>
    </li>
  </ul>
</div>
"""

_GAGALAB_TAB_HTML = """
<div class="Tabs-content">
  <p>Application fee: ILS 150 (non-refundable), due at the time of application</p>
  <p>Early Bird rate, until April 13: ILS 2340</p>
  <p>Full tuition to be paid to Gaga between April 3 and June 28: ILS 2600</p>
  <p>Room &amp; Board The fee for room &amp; board is to be paid to Orsolina28 by June 28: € 990</p>
</div>
"""


def test_tab_prices_standard() -> None:
    tree = HTMLParser(_STANDARD_TAB_HTML)
    node = tree.css_first(".Tabs-content")
    assert node is not None
    prices = _tab_prices(node)
    amounts = {(p.amount, p.currency) for p in prices}
    assert (40.0, "EUR") in amounts
    assert (1500.0, "EUR") in amounts
    assert (1400.0, "EUR") in amounts
    # No duplicate 1400 (once from leaf li, not again from p)
    eur1400 = [p for p in prices if p.amount == 1400.0 and p.currency == "EUR"]
    assert len(eur1400) == 1


def test_tab_prices_gagalab() -> None:
    tree = HTMLParser(_GAGALAB_TAB_HTML)
    node = tree.css_first(".Tabs-content")
    assert node is not None
    prices = _tab_prices(node)
    amounts = {(p.amount, p.currency) for p in prices}
    assert (150.0, "ILS") in amounts
    assert (2340.0, "ILS") in amounts
    assert (2600.0, "ILS") in amounts
    assert (990.0, "EUR") in amounts


def test_tab_prices_standard_labels() -> None:
    tree = HTMLParser(_STANDARD_TAB_HTML)
    node = tree.css_first(".Tabs-content")
    assert node is not None
    prices = _tab_prices(node)
    by_amount = {p.amount: p for p in prices}
    assert by_amount[1500.0].label == "Tuition (full board)"
    assert by_amount[1400.0].label == "Early Bird tuition"
    assert by_amount[40.0].label == "Application fee"
    # Tuition includes accommodation + meals
    assert "accommodation" in by_amount[1500.0].includes
    assert "meals" in by_amount[1500.0].includes


# ---------------------------------------------------------------------------
# _edition_slugs
# ---------------------------------------------------------------------------

_INDEX_SNIPPET = """
<html><body>
<a href="/en/programs/professional-training/intensive/">Index</a>
<a href="/en/programs/professional-training/intensive/jiri-kylian/">Kylian</a>
<a href="/en/programs/professional-training/intensive/marco-goecke/">Goecke</a>
<a href="/en/programs/professional-training/intensive/archive/">Archive</a>
<a href="/en/programs/professional-training/intensive/pina-bausch/">Pina Bausch</a>
<a href="/it/programmi/corsi-per-professionisti/intensive/">Italian index</a>
<a href="https://www.orsolina28.it/en/programs/professional-training/intensive/">Abs index</a>
</body></html>
"""


def test_edition_slugs_finds_editions() -> None:
    slugs = _edition_slugs(_INDEX_SNIPPET)
    assert "jiri-kylian" in slugs
    assert "marco-goecke" in slugs
    assert "pina-bausch" in slugs


def test_edition_slugs_skips_archive() -> None:
    slugs = _edition_slugs(_INDEX_SNIPPET)
    assert "archive" not in slugs


def test_edition_slugs_skips_index_itself() -> None:
    """The intensive/ path with no trailing slug should not produce an empty slug."""
    slugs = _edition_slugs(_INDEX_SNIPPET)
    assert "" not in slugs


def test_edition_slugs_sorted() -> None:
    slugs = _edition_slugs(_INDEX_SNIPPET)
    assert slugs == sorted(slugs)


# ---------------------------------------------------------------------------
# _build_offering (integration over a page fixture)
# ---------------------------------------------------------------------------

# Minimal page HTML that exercises the full _build_offering path.
_MINIMAL_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head></head>
<body>
<h1>Jiri Kylian</h1>
<h2 class="PageHeaderEventSplit-subtitle">Intensive 2026</h2>
<div class="PageHeaderEventSplit-date Date">June 14 – June 21, 2026</div>
<ul class="PeopleList-list">
  <li class="PeopleList-item">
    <h3 class="PeopleList-title">Parvaneh Scharafali</h3>
    <p class="PeopleList-subtitle">Teaching Artist</p>
  </li>
  <li class="PeopleList-item">
    <h3 class="PeopleList-title">Mario Alberto Zambrano</h3>
    <p class="PeopleList-subtitle">Program Director</p>
  </li>
</ul>
<div class="Tabs-content" data-index="1">
  <ul>
    <li>February 4, 2026 at 6:00 P.M. (CET): Deadline for the submission of an application;</li>
    <li>Application Fee: €40 (non-refundable)</li>
    <li>Tuition: € 1.500
      <ul>
        <li>Early Bird, by March 17, 2026: € 1.400</li>
      </ul>
    </li>
  </ul>
</div>
<div class="Tabs-content" data-index="2">
  <p>Who Can Apply: The program is intended for dancers aged 18 and over.</p>
</div>
<a href="https://booking.orsolina28.it/en/course/31">Apply</a>
<div class="body">
<h3>The program</h3>
<p>A week dedicated to the study and practice of Jiří Kylián's work and repertoire sessions.</p>
</div>
</body>
</html>
"""


def test_build_offering_basic() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert o.id == "orsolina28/jiri-kylian"
    assert o.schedule.start == date(2026, 6, 14)
    assert o.schedule.end == date(2026, 6, 21)
    assert o.schedule.season == "2026"
    assert o.schedule.timezone == "Europe/Rome"


def test_build_offering_title() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert o.title == "Jiri Kylian — Intensive 2026"


def test_build_offering_genres() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert "contemporary" in o.genres
    assert "repertoire" in o.genres


def test_build_offering_teachers() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert len(o.teachers) == 2
    names = {t.name for t in o.teachers}
    assert "Parvaneh Scharafali" in names
    assert "Mario Alberto Zambrano" in names
    roles = {t.name: t.role for t in o.teachers}
    assert roles["Parvaneh Scharafali"] == "Teaching Artist"
    assert roles["Mario Alberto Zambrano"] == "Program Director"


def test_build_offering_prices() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    amounts = {(p.amount, p.currency) for p in o.prices}
    assert (40.0, "EUR") in amounts
    assert (1500.0, "EUR") in amounts
    assert (1400.0, "EUR") in amounts


def test_build_offering_deadline() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert o.application.deadline == date(2026, 2, 4)


def test_build_offering_apply_url() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert o.application.url == "https://booking.orsolina28.it/en/course/31"


def test_build_offering_requirements() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert len(o.application.requirements) == 1
    assert o.application.requirements[0].type == "video"


def test_build_offering_age_range() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert o.age_range is not None
    assert o.age_range["min"] == 18
    assert o.age_range["max"] is None


def test_build_offering_level() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert "pre-professional" in o.level
    assert "open" in o.level


def test_build_offering_organisation() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert o.organization.slug == "orsolina28"
    assert o.organization.country == "IT"


def test_build_offering_location() -> None:
    o = _build_offering(
        _MINIMAL_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/jiri-kylian/",
        "jiri-kylian",
    )
    assert o is not None
    assert o.location is not None
    assert o.location.city == "Moncalvo"
    assert o.location.country == "IT"


def test_build_offering_undated_returns_none() -> None:
    """A page with no parseable date header must return None."""
    html = """
    <html><body>
    <h1>Some Intensive</h1>
    <div class="Tabs-content"><p>TBD</p></div>
    </body></html>
    """
    result = _build_offering(
        html,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/unknown/",
        "unknown",
    )
    assert result is None


# ---------------------------------------------------------------------------
# Edge: GagaLab HTML structure (ILS fees + gagapeople apply link)
# ---------------------------------------------------------------------------

_GAGALAB_PAGE_HTML = """
<!DOCTYPE html>
<html><body>
<h1>GagaLab Summer 2026</h1>
<h2 class="PageHeaderEventSplit-subtitle">Intensive 2026</h2>
<div class="PageHeaderEventSplit-date Date">July 12 – July 19, 2026</div>
<ul class="PeopleList-list">
  <li class="PeopleList-item">
    <h3 class="PeopleList-title">Ohad Naharin</h3>
    <p class="PeopleList-subtitle">Guest Choreographer</p>
  </li>
</ul>
<div class="Tabs-content" data-index="1">
  <p>Application fee: ILS 150 (non-refundable), due at the time of application</p>
  <p>Early Bird rate, until April 13: ILS 2340</p>
  <p>Full tuition to be paid to Gaga: ILS 2600</p>
  <p>Room &amp; Board: € 990</p>
  <ul>
    <li>In case of cancellation before April 22, 2026, a 90% refund will be issued;</li>
  </ul>
</div>
<div class="Tabs-content" data-index="2">
  <p>The program is intended for dancers aged 18 and over.</p>
</div>
<a href="https://www.gagapeople.com/en/event/gagalab-summer-2026-in-italy/">Apply</a>
<div>
<h3>The program</h3>
<p>GagaLab: six days of intensive physical research in a dance haven. Based on Gaga movement language.</p>
</div>
</body></html>
"""


def test_build_offering_gagalab_apply_url() -> None:
    o = _build_offering(
        _GAGALAB_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/gagalab-summer-2026/",
        "gagalab-summer-2026",
    )
    assert o is not None
    assert o.application.url is not None
    assert "gagapeople" in (o.application.url or "")


def test_build_offering_gagalab_deadline_none() -> None:
    """GagaLab has no submission-deadline bullet → deadline must be None."""
    o = _build_offering(
        _GAGALAB_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/gagalab-summer-2026/",
        "gagalab-summer-2026",
    )
    assert o is not None
    assert o.application.deadline is None


def test_build_offering_gagalab_ils_prices() -> None:
    o = _build_offering(
        _GAGALAB_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/gagalab-summer-2026/",
        "gagalab-summer-2026",
    )
    assert o is not None
    currencies = {p.currency for p in o.prices}
    assert "ILS" in currencies
    assert "EUR" in currencies


def test_build_offering_gagalab_genres() -> None:
    o = _build_offering(
        _GAGALAB_PAGE_HTML,
        "https://www.orsolina28.it/en/programs/professional-training/intensive/gagalab-summer-2026/",
        "gagalab-summer-2026",
    )
    assert o is not None
    assert "contemporary" in o.genres
