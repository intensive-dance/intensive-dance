from datetime import date

import pytest

from intensive_dance.scrapers import bobbio_summer_ballet_intensive as bobbio

HOME = """
<div class="elementor">
  <h1>Bobbio Summer Ballet Intensive</h1>
  <div>Summer Camp 2026</div>
  <div>Summer Camp 2026: dal 14 al 24 Luglio</div>
  <p>Benvenuti alla seconda edizione di Bobbio Summer Ballet Intensive 2026.</p>
  <p>Il nostro corso estivo di danza è pensato per ballerini di tutti i livelli,
  dai principianti agli avanzati. Il percorso prevede lezioni di: danza classica,
  punte, tecnica per uomini, variazioni, repertorio, danza contemporanea,
  passo a due, pilates, yoga, Horton.</p>
  <p>Introduzione al Balletto. Perfezionamento Balletto. Innovazione in Danza Contemporanea.</p>
</div>
"""

REGISTRATION = """
<div class="elementor">
  <p>Scadenza il 30 GIUGNO. I posti sono limitati.</p>
  <p>Per iscriversi, è necessario compilare il modulo di registrazione e allegare
  3 foto: un ritratto, una in quarta posizione croisée en relevé e una in primo
  arabesque. Le punte non sono obbligatorie per le foto. Le candidature sono aperte.</p>
  <p>Per completare l'iscrizione, bisogna pagare la quota di registrazione di 150€.</p>
  <p>In caso di cancellazione verrà effettuato un rimborso del 50% dell'importo pagato.</p>
</div>
"""

DOCENTI = """
<div class="elementor">
  <h2>Dora Ciacca</h2>
  <h2>Christopher Vazquez</h2>
  <h2>Iratxe Ansa e Igor Bacovich</h2>
  <h2>Selina Shida Hack</h2>
</div>
"""

TODAY = date(2026, 6, 16)


def _build():
    return bobbio._build_offerings(
        bobbio._page_text(HOME), bobbio._page_text(REGISTRATION), DOCENTI, TODAY
    )


def test_one_offering_with_dates_and_id():
    offerings = _build()
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "bobbio-summer-ballet-intensive/2026"
    assert o.title == "Bobbio Summer Ballet Intensive 2026"
    assert o.schedule.season == "summer"
    assert o.schedule.start == date(2026, 7, 14)
    assert o.schedule.end == date(2026, 7, 24)


def test_genres_from_curriculum():
    o = _build()[0]
    assert set(o.genres) == {"classical", "pointe", "contemporary", "repertoire"}


def test_levels_span_beginner_to_advanced():
    o = _build()[0]
    assert set(o.level) == {"beginner", "intermediate", "advanced"}


def test_application_status_deadline_and_fee_note():
    app = _build()[0].application
    assert app.status == "open"
    assert app.deadline == date(2026, 6, 30)
    assert app.url.endswith("/registrazione/")
    assert app.notes is not None
    assert "150" in app.notes
    assert "50%" in app.notes


def test_requirements_headshot_plus_defined_poses():
    reqs = _build()[0].application.requirements
    types = [r.type for r in reqs]
    assert types == ["headshot", "photos"]
    photos = reqs[1]
    assert photos.specificity == "defined-poses"
    assert "first arabesque" in photos.poses
    assert photos.notes is not None and "Pointe" in photos.notes


def test_teachers_include_director_role_and_split_duo():
    teachers = _build()[0].teachers
    names = [t.name for t in teachers]
    assert "Iratxe Ansa" in names and "Igor Bacovich" in names
    director = next(t for t in teachers if t.name == "Dora Ciacca")
    assert director.role == "Artistic director"


def test_missing_year_marker_raises_rather_than_emptying_store():
    # A degraded fetch (no "Summer Camp YYYY" marker) must raise so run.py keeps
    # the prior store instead of committing an empty one (#316), not return [].
    home_no_year = HOME.replace("Summer Camp 2026", "Summer Camp")
    with pytest.raises(ValueError, match="edition marker"):
        bobbio._build_offerings(bobbio._page_text(home_no_year), "", DOCENTI, TODAY)


def test_location_is_bobbio_italy():
    o = _build()[0]
    assert o.location is not None
    assert o.location.city == "Bobbio"
    assert o.location.country == "IT"
    assert o.prices == []
