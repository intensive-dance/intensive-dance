"""Unit tests for the Munich Ballet Intensive scraper (Google Sites microsite).

Offline, inline HTML snippets mirroring the three live pages — no network. They
pin: the numeric DD.MM.YYYY date span, the two age-Gruppe prices folded into one
Offering, the curriculum-driven genres, the digit-split age band ("1 3 - 1 7"
that Google Sites renders), the advanced level, the two directors with their
company affiliations, and the open-application + no-audition requirement. The
"missing dates" edge yields no Offering.
"""

from __future__ import annotations

from intensive_dance.models import NoneReq
from intensive_dance.scrapers import munich_ballet_intensive as mbi

# Startseite — the dated banner, the advanced-students line and the open-
# application phrase.
HOME = (
    "<html><body>"
    "<h1>Munich Ballet Intensive</h1>"
    "<p>with Katja &amp; Maxim</p>"
    "<h2>Summer Intensiv</h2>"
    "<p>03.08.2026 - 08.08.2026</p>"
    "<p>Zweimal jährlich findet unser intensiv Ballet-Workshop in München statt "
    "und bietet eine einzigartige Gelegenheit für fortgeschrittene "
    "Ballettstudenten.</p>"
    "<p>Unsere Anmeldung ist geöffnet.</p>"
    "<a>Jetzt anmelden!</a>"
    "</body></html>"
)

# Preise — the curriculum list, the two Gruppe bands (Gruppe 2's digits split as
# Google Sites renders them) and the repeated date span.
PRICES = (
    "<html><body>"
    "<h2>Preise</h2>"
    "<p>In unserem Intensiv Workshop erwarten euch unter anderem:</p>"
    "<p>Floor work</p><p>Ballet class</p><p>Technique &amp; Coordination</p>"
    "<p>Repertoire</p><p>Point work</p>"
    "<p>Gruppe 1</p><p>10 - 13 Jahre</p><p>300 €</p>"
    "<p>Gruppe 2</p><p>1 3 - 1 7 Jahre</p><p>350 €</p>"
    "<p>03.08.2026 - 08.08.2026</p>"
    "</body></html>"
)

# Über uns — the two director biographies, with their company names so the
# affiliations attach.
ABOUT = (
    "<html><body>"
    "<h2>Über uns</h2>"
    "<h3>Katherina Markowskaja</h3>"
    "<p>Ausbildung an der Ballett-Akademie München. Erste Solistin an der "
    "Sächsischen Staatsoper Dresden. 2010 zum Bayerischen Staatsballett.</p>"
    "<h3>Maxim Chashchegorov</h3>"
    "<p>Ausbildung an der St. Petersburger Ballettakademie, Corps de ballet des "
    "Mariinsky Balletts, danach Bayerisches Staatsballett.</p>"
    "</body></html>"
)


def _offering():
    return mbi._build_offering(HOME, PRICES, ABOUT)


def test_emits_one_dated_offering():
    o = _offering()
    assert o is not None
    assert o.id == "munich-ballet-intensive/summer-intensive-2026"
    assert o.title == "Summer Intensiv 2026"
    assert o.schedule.season == "2026"


def test_dates_numeric_span():
    o = _offering()
    assert o is not None
    assert o.schedule.start is not None and o.schedule.start.isoformat() == "2026-08-03"
    assert o.schedule.end is not None and o.schedule.end.isoformat() == "2026-08-08"
    assert o.schedule.timezone == "Europe/Berlin"


def test_age_range_widest_band():
    # Overall 10–17: min of Gruppe 1, max of (digit-split) Gruppe 2.
    assert _offering().age_range == {"min": 10, "max": 17}  # type: ignore[union-attr]


def test_level_advanced():
    assert _offering().level == ["advanced"]  # type: ignore[union-attr]


def test_genres_from_curriculum():
    o = _offering()
    assert o is not None
    assert "classical" in o.genres
    assert "repertoire" in o.genres
    assert "pointe" in o.genres


def test_two_prices_per_gruppe():
    o = _offering()
    assert o is not None
    assert [(p.amount, p.currency, p.label) for p in o.prices] == [
        (300.0, "EUR", "Gruppe 1 (10-13 years)"),
        (350.0, "EUR", "Gruppe 2 (13-17 years)"),
    ]
    assert all(p.includes == ["tuition"] for p in o.prices)


def test_location_munich():
    o = _offering()
    assert o is not None
    assert o.location is not None
    assert o.location.city == "Munich"
    assert o.location.country == "DE"
    assert "Unterschleißheim" in (o.location.venue or "")


def test_teachers_with_affiliations():
    o = _offering()
    assert o is not None
    names = [t.name for t in o.teachers]
    assert names == ["Katherina Markowskaja", "Maxim Chashchegorov"]
    orgs = {a.organization for t in o.teachers for a in t.affiliations}
    assert "Bavarian State Ballet" in orgs
    assert "Mariinsky Ballet" in orgs


def test_application_open_no_audition():
    o = _offering()
    assert o is not None
    assert o.application.status == "open"
    assert o.application.url == "https://www.danceartsacademy.de/anmeldungsformular"
    assert len(o.application.requirements) == 1
    assert isinstance(o.application.requirements[0], NoneReq)


def test_no_dates_no_offering():
    home_no_date = HOME.replace("<p>03.08.2026 - 08.08.2026</p>", "")
    prices_no_date = PRICES.replace("<p>03.08.2026 - 08.08.2026</p>", "")
    assert mbi._build_offering(home_no_date, prices_no_date, ABOUT) is None
