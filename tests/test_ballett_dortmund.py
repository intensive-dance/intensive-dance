from intensive_dance.scrapers import ballett_dortmund as bd

# Both editions on one page; only the Internationale Sommerakademie is emitted
# here (the Junior course belongs to the dbft-sommerakademie provider).
HTML = """
<html><body>
<div id="c1" class="frame frame--type-text">
  <h3>Internationale Sommerakademie</h3>
  <p><strong>Termin</strong> 24-29. August 2026<br><strong>Ort</strong> Ballettzentrum Westfalen<br><strong>Alter</strong> ab 15 Jahren</p>
  <p><strong>Kurse</strong> Klassischer Tanz, Moderne Tanz, Repertoire, Point Work, Choreografische Workshops, Edward-Clug-Style, Jiri-Kylian-Style</p>
  <p><strong>Kursgebühr </strong>590 €</p>
  <p><strong>Im Preis enthalten</strong></p>
  <ul><li>alle Kurse</li><li>tägliches Mittagsessen</li></ul>
  <p><a href="/ballett/.../anmeldung/">Anmeldung</a></p>
</div>
<div id="c2" class="frame frame--type-text">
  <h3>Sommerakademie Junior</h3>
  <p><strong>Termin</strong> 24.-29. August 2026<br><strong>Ort</strong> Opernhaus Dortmund<br><strong>Alter</strong> 12 - 15 Jahren (Bewerbungspflicht)</p>
  <p><strong>Kursgebühr</strong> 360 €</p>
</div>
</body></html>
"""


def test_emits_only_the_open_edition():
    offerings = bd._build_offerings(HTML)
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "ballett-dortmund/internationale-sommerakademie-2026"
    assert o.title == "Internationale Sommerakademie 2026"


def test_dates_age_price_genres_and_open_application():
    o = bd._build_offerings(HTML)[0]

    assert o.schedule.season == "2026"
    assert o.schedule.start is not None and o.schedule.start.isoformat() == "2026-08-24"
    assert o.schedule.end is not None and o.schedule.end.isoformat() == "2026-08-29"

    assert o.age_range == {"min": 15, "max": None}

    assert len(o.prices) == 1
    assert o.prices[0].amount == 590.0
    assert o.prices[0].currency == "EUR"
    assert "tuition" in o.prices[0].includes and "meals" in o.prices[0].includes

    assert set(o.genres) == {"classical", "contemporary", "repertoire", "pointe"}

    assert o.location is not None
    assert o.location.venue == "Ballettzentrum Westfalen"
    assert o.location.city == "Dortmund"

    # Open registration: explicitly no audition/photo/video gate.
    assert [r.type for r in o.application.requirements] == ["none"]


def test_missing_section_yields_nothing():
    assert bd._build_offerings("<html><body><p>nichts hier</p></body></html>") == []
