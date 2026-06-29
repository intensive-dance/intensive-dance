"""Offline tests for the Sommer Tanz Camp (Ballett Days Berlin) scraper.

Inline HTML snippets mirror the real flowweb.de structure: the calendar's
`<div align="center">` edition blocks, the registration page's flat
price/title/dates/wann/wo run, and the program page's trainer `<ol><li>` list.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import sommer_tanz_camp_berlin as stc

TODAY = date(2026, 6, 26)

# Calendar page: one ballet edition + one BREAKING edition (must be dropped).
TERMINE_HTML = """
<div align="center"><b><u>OSTER INTENSIVE BALLETT TAGE BERLIN&nbsp;&nbsp;</u></b><br>
(ab 14 Jahre Mittelstufe bis Fortgeschritten)<br>
&gt;&gt;&gt;30.03.2026-02.04..2026 &lt;&lt;&lt; SAMUELS DANCE HALL Berlin Tempelhof</div>
<div align="center"><b><u>OSTER INTENSIVE BREAKING TAGE BERLIN</u></b><br>
(ab 12 Jahren Einsteiger - Mittelstufe)<br>
&gt;&gt;&gt;07.04.2026-10.04..2026 &lt;&lt;&lt; SAMUELS DANCE HALL Berlin Tempelhof</div>
"""

# Registration page: a no-date summer item, the Herbst ballet item (priced),
# then a BREAKING item with a year-less shorthand date — only the ballet matches.
ANMELDUNG_HTML = """<body>
<h3>475,00 &euro; SOMMERTANZ CAMPS 8 Tage all inklusive</h3>
<h3>180,00 &euro; Herbst Ballett Intensive Days in Berlin</h3>
<h3>26.10.2026-29.10.2026</h3>
<div>wann: t&auml;glich 10.00-14.00 Uhr mit Berliner Topcoaches der Samuels Dance Hall</div>
<div>wo: Samuel`s Dance Hall Tempelhof Burgemeister Stra&szlig;e 4 12099 Berlin.</div>
<p>Download ANMELDEFORMULAR BALLETTCAMP 2026</p>
<h3>180,00 &euro; Herbst BREAKING DAYS EINSTEIGER ab 9 Jahre 26.-29.10.2026</h3>
</body>"""

# Program page: format description (genres) + trainer list, with the matching dates.
DETAIL_HTML = """<body>
<div align="center">Ballett Days Berlin</div>
<div align="center">Erlebe 4 intensive Tage voller Ballett, Modern und Contemporary.</div>
<div align="center">Eure Trainer</div>
<ol>
<li>Sandra - Samuels Crew Member</li>
<li>Cindy - Deutsche Meisterin bei der ASDU &amp; Choreographin auf Mein Schiff</li>
<li>Laura - M.A. der Palucca Hochschule f&uuml;r Tanz Dresden &amp; zweifache Siegerin beim Tanz-Olymp</li>
</ol>
<div align="center">TERMINE 30.03. - 02.04.2026 4 Tage 10 - 14 Uhr</div>
</body>"""


def test_dates_tolerates_double_dot():
    assert stc._dates(">>>30.03.2026-02.04..2026 <<<") == (date(2026, 3, 30), date(2026, 4, 2))


def test_ages_open_topped():
    assert stc._ages("ab 14 Jahre Mittelstufe") == {"min": 14, "max": None}
    assert stc._ages("keine Angabe") is None


def test_levels_range():
    assert stc._levels("Mittelstufe bis Fortgeschritten") == ["intermediate", "advanced"]
    assert stc._levels("Einsteiger") == ["beginner"]


def test_cycle_tag_distinguishes_seasons():
    assert stc._cycle_tag("Oster Intensive Ballett", date(2026, 3, 30)) == ("spring", "Oster 2026")
    assert stc._cycle_tag("Herbst Ballett Days", date(2026, 10, 26)) == ("autumn", "Herbst 2026")


def test_termine_drops_breaking_and_reads_oster():
    eds = stc._termine_editions(TERMINE_HTML)
    assert len(eds) == 1
    ed = eds[0]
    assert ed["start"] == date(2026, 3, 30) and ed["end"] == date(2026, 4, 2)
    assert ed["ageRange"] == {"min": 14, "max": None}
    assert ed["level"] == ["intermediate", "advanced"]
    assert ">>>" not in ed["notes"]


def test_anmeldung_reads_priced_ballet_only():
    eds = stc._anmeldung_editions(ANMELDUNG_HTML)
    assert len(eds) == 1
    ed = eds[0]
    assert ed["start"] == date(2026, 10, 26) and ed["end"] == date(2026, 10, 29)
    assert ed["price"][0].amount == 180.0 and ed["price"][0].currency == "EUR"


def test_detail_program_genres_and_trainers():
    prog = stc._detail_program(DETAIL_HTML)
    assert prog is not None
    assert prog["start"] == date(2026, 3, 30) and prog["end"] == date(2026, 4, 2)
    assert set(prog["genres"]) == {"classical", "contemporary"}
    names = [t.name for t in prog["teachers"]]
    assert names == ["Sandra", "Cindy", "Laura"]
    laura = prog["teachers"][2]
    assert laura.affiliations[0].organization == "Palucca Hochschule für Tanz Dresden"


def test_build_offerings_two_editions():
    offerings = stc._build_offerings(TERMINE_HTML, ANMELDUNG_HTML, DETAIL_HTML, TODAY)
    assert len(offerings) == 2
    spring, autumn = offerings  # sorted by start date

    assert spring.id == "sommer-tanz-camp-berlin/ballett-2026-spring"
    assert set(spring.genres) == {"classical", "contemporary"}  # from the program page
    assert spring.age_range == {"min": 14, "max": None}
    assert spring.level == ["intermediate", "advanced"]
    assert [t.name for t in spring.teachers] == ["Sandra", "Cindy", "Laura"]
    assert spring.prices == []  # no price stated for the Oster edition

    assert autumn.id == "sommer-tanz-camp-berlin/ballett-2026-autumn"
    assert autumn.genres == ["classical"]  # labelled only "Ballett" on its own page
    assert autumn.prices[0].amount == 180.0
    assert autumn.teachers == []
    assert autumn.application.requirements[0].type == "none"


def test_overlapping_edition_merges_price_onto_calendar_entry():
    """Same dated edition on both pages → one Offering, fields unioned."""
    termine = """
    <div align="center"><b><u>HERBST BALLETT INTENSIVE DAYS</u></b><br>
    (ab 12 Jahre Mittelstufe)<br>
    &gt;&gt;&gt;26.10.2026-29.10.2026 &lt;&lt;&lt; SAMUELS DANCE HALL Berlin Tempelhof</div>
    """
    offerings = stc._build_offerings(termine, ANMELDUNG_HTML, DETAIL_HTML, TODAY)
    assert len(offerings) == 1
    o = offerings[0]
    assert o.age_range == {"min": 12, "max": None}  # from the calendar
    assert o.prices[0].amount == 180.0  # from the registration page


def test_degraded_fetch_raises_not_empties():
    with pytest.raises(RuntimeError):
        stc._build_offerings("<div></div>", "<body></body>", "<body></body>", TODAY)
