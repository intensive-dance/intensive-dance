from datetime import date

from intensive_dance.scrapers import tanzquartier_koeln as tq

# Mirrors the live workshop detail page (labelled date / age / level / price block).
_HTML = """
<html><body>
<h1>Ballett &amp; Contemporary Intensiv-Workshop</h1>
<p>f&uuml;r Jugendliche und Erwachsene - Level Mittelstufe vom 24.-28. August 2026</p>
<p>Klassisches Ballett ist ausgebucht! Es gibt nur noch einige wenige Pl&auml;tze f&uuml;r Contemporary!</p>
<p>f&uuml;r Jugendliche (ab 15 Jahren) und Erwachsene mit guten Vorkenntnissen.</p>
<p>10:00 - 12:30 Uhr klassisches Ballett. 13:00 - 15:00 Uhr Contemporary.</p>
<p>Alter: Jugendliche (ab 15 Jahren) und Erwachsene</p>
<p>Level: Mittelstufe (gute Vorkenntnisse im Ballett und/ oder Contemporary)</p>
<p>Tanzquartier Elsa&szlig;stra&szlig;e</p>
<p>Preis:</p>
<p>Beide Module: 185,- EUR / Mitglieder 169,- EUR</p>
<p>Klassisches Ballett: 110,- EUR / Mitglieder 99,- EUR</p>
<p>Contemporary: 89,- EUR / Mitglieder 79,- EUR</p>
</body></html>
"""


def test_single_offering_core_fields():
    offerings = tq._build_offerings(_HTML)
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "tanzquartier-koeln/ballett-contemporary-intensiv-workshop-2026"
    assert o.title == "Ballett & Contemporary Intensiv-Workshop"
    assert set(o.genres) == {"classical", "contemporary"}
    assert o.level == ["intermediate"]
    # Open-topped age band.
    assert o.age_range == {"min": 15, "max": None}
    assert o.schedule.start == date(2026, 8, 24)
    assert o.schedule.end == date(2026, 8, 28)
    assert o.schedule.season == "2026"


def test_prices_with_member_notes():
    o = tq._build_offerings(_HTML)[0]
    by_label = {p.label: p for p in o.prices}
    assert by_label["Beide Module (Ballett & Contemporary)"].amount == 185.0
    assert by_label["Klassisches Ballett"].amount == 110.0
    assert by_label["Contemporary"].amount == 89.0
    assert all(p.currency == "EUR" and p.includes == ["tuition"] for p in o.prices)
    assert by_label["Contemporary"].notes == "Mitglieder: 79 EUR"


def test_application_open_with_soldout_note():
    o = tq._build_offerings(_HTML)[0]
    assert o.application.status == "open"
    assert o.application.requirements == []  # prerequisite, not an audition gate
    assert o.application.notes is not None
    assert "ausgebucht" in o.application.notes
    assert o.location is not None
    assert o.location.city == "Cologne"
    assert o.location.country == "DE"
