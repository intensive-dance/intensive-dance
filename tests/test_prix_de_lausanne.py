"""Unit tests for the Prix de Lausanne scraper (WordPress REST, one page).

These pin the parsing of the practical-information paragraph — the date span
(year on the closing date only), the edition title, the venue — plus the
discovery rule that only the next, not-yet-run edition is emitted as a
`competition`. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import prix_de_lausanne as pdl

PAGE = {
    "link": "https://www.prixdelausanne.org/practical_information/",
    "content": {
        "rendered": (
            "<div><p>The <strong>Prix de Lausanne 2027</strong> will take place from"
            "<strong> 31 January to 7 February 2027</strong>, at Beaulieu Lausanne, "
            "Switzerland.</p></div>"
        )
    },
}


def test_dates_year_on_closing_date_only():
    text = "will take place from 31 January to 7 February 2027, at Beaulieu Lausanne"
    assert pdl._dates(text) == (date(2027, 1, 31), date(2027, 2, 7))


def test_dates_absent():
    assert pdl._dates("no dates announced yet") == (None, None)


def test_title_and_location():
    text = "The Prix de Lausanne 2027 will take place from … at Beaulieu Lausanne, Switzerland."
    assert pdl._title(text, "2027") == "Prix de Lausanne 2027"
    loc = pdl._location(text)
    assert (loc.venue, loc.city, loc.country) == ("Beaulieu Lausanne", "Lausanne", "CH")


def test_build_emits_competition_offering():
    offerings = pdl._build_offerings(PAGE, date(2026, 6, 5))
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "prix-de-lausanne/2027"
    assert o.kind == "competition"
    assert o.genres == ["classical", "contemporary"]
    assert (o.schedule.start, o.schedule.end, o.schedule.season) == (
        date(2027, 1, 31),
        date(2027, 2, 7),
        "2027",
    )
    assert o.lifecycle == "scheduled"
    # We don't invent fees/requirements/deadline that aren't on the live page.
    assert o.prices == []
    assert o.application.requirements == []
    assert o.application.status is None


def test_build_drops_past_edition():
    # End date already behind "today" → the edition has run, so nothing is emitted.
    assert pdl._build_offerings(PAGE, date(2027, 3, 1)) == []
