from datetime import date

from intensive_dance.scrapers import dbft_sommerakademie as dbft

# Mirrors the live page structure (numeric DD.MM.YYYY span, deadline in the same
# format, age sentence, fee, Tally application form link).
_HTML = """
<html><body>
<h1>Sommerakademie Junior</h1>
<p>Aktuelles Programm 2026 Eine intensive Ballettwoche f&uuml;r Talente im klassischen Tanz</p>
<p>Mit der Sommerakademie Junior 2026 bietet der DBfT ein hochwertiges Sommerprogramm
f&uuml;r besonders engagierte Nachwuchst&auml;nzer*innen im Alter von 13 bis 15 Jahren
mit sehr guten Vorkenntnissen im Klassischen Tanz.</p>
<p>Zeitraum: Mo, 24.08.2026 bis Sa, 29.08.2026 (letzte Ferienwoche in Nordrhein-Westfalen)
Ort: Ballettsaal im Theater Dortmund (oder Ballettzentrum Westfalen)
Zeit: t&auml;glich 10:00 &ndash; ca. 16:00 Uhr
Kursgeb&uuml;hr: 360 &euro;</p>
<p>Wichtig: Bewerbung erforderlich (<a href="https://tally.so/r/xXdK6G">Online-Bewerbungsformular</a>)
- nur bis 15.06.2026 m&ouml;glich!</p>
</body></html>
"""


def test_single_offering_core_fields():
    offerings = dbft._build_offerings(_HTML)
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "dbft-sommerakademie/sommerakademie-junior-2026"
    assert o.title == "Sommerakademie Junior 2026"
    assert o.genres == ["classical"]
    assert o.age_range == {"min": 13, "max": 15}
    assert o.schedule.season == "2026"
    assert o.schedule.start == date(2026, 8, 24)
    assert o.schedule.end == date(2026, 8, 29)
    assert o.schedule.timezone == "Europe/Berlin"


def test_location_price_application():
    o = dbft._build_offerings(_HTML)[0]
    assert o.location is not None
    assert o.location.city == "Dortmund"
    assert o.location.venue is not None
    assert "Theater Dortmund" in o.location.venue
    # The deadline must come from the application sentence, not be confused with
    # the same-format course dates; the form URL is the Tally link.
    assert o.application.deadline == date(2026, 6, 15)
    assert o.application.url == "https://tally.so/r/xXdK6G"
    # Form questions load via JS and aren't stated → unknown requirements.
    assert o.application.requirements == []
    assert len(o.prices) == 1
    assert o.prices[0].amount == 360.0
    assert o.prices[0].currency == "EUR"
    assert o.prices[0].includes == ["tuition"]


def test_missing_dates_falls_open_year_from_heading():
    # No "Zeitraum:" sentence: emission is driven by discovery, not date parsing,
    # so the Offering still exists with null dates and the year read from the heading.
    html = """
    <html><body>
    <p>Aktuelles Programm 2027 Eine intensive Ballettwoche im klassischen Tanz
    f&uuml;r T&auml;nzer*innen im Alter von 13 bis 15 Jahren.</p>
    </body></html>
    """
    o = dbft._build_offerings(html)[0]
    assert o.id == "dbft-sommerakademie/sommerakademie-junior-2027"
    assert o.schedule.season == "2027"
    assert o.schedule.start is None
    assert o.schedule.end is None
    assert o.application.deadline is None
    assert o.prices == []
