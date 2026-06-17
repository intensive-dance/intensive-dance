from intensive_dance.scrapers import centro_formazione_danza_verona as cf

URL = "https://cfdanzaverona.it/summer-school/"

HTML = """
<div>
  <p>Due settimane di alta formazione per giovani danzatori. Dal 29 giugno all'11 luglio 2026,
  la Ballet Summer School porta a Verona un programma intensivo.</p>
  <p>Date 29 giugno – 11 luglio 2026</p>
  <p>Quote 450 euro per una settimana + 25 euro di iscrizione</p>
  <p>Programma. Classico e punte: lezioni di danza classica, tecnica di punte. Repertorio e
  passo a due. Tecnica maschile. Contemporaneo: movimento contemporaneo.</p>
  <p>Audizioni 10 luglio 2026 presso la sede del Centro Formazione Danza Verona, Via Berbera 19/b,
  durante la Ballet Summer School 2026.</p>
  <p>1 sessione 29 giugno – 4 luglio 2026</p>
  <p>2 sessione 6 luglio – 11 luglio 2026</p>
  <p>Entrambe: sconto del 30% sulla quota corso. La quota di iscrizione resta pari a 25 euro.</p>
</div>
"""


def _offering():
    out = cf._build_offerings(HTML, URL)
    assert len(out) == 1
    return out[0]


def test_overall_span_and_two_sessions():
    o = _offering()
    assert o.id == "centro-formazione-danza-verona/2026"
    assert o.schedule.start is not None and o.schedule.end is not None
    assert (o.schedule.start.isoformat(), o.schedule.end.isoformat()) == (
        "2026-06-29",
        "2026-07-11",
    )
    sessions = [(s.label, s.start.isoformat(), s.end.isoformat()) for s in o.schedule.sessions]
    assert sessions == [
        ("Session 1", "2026-06-29", "2026-07-04"),
        ("Session 2", "2026-07-06", "2026-07-11"),
    ]


def test_genres_from_programma():
    assert _offering().genres == ["classical", "pointe", "contemporary", "repertoire"]


def test_prices_week_and_registration():
    prices = {p.label: p for p in _offering().prices}
    assert prices["Per week"].amount == 450.0 and prices["Per week"].includes == ["tuition"]
    assert prices["Registration fee"].amount == 25.0
    assert "30%" in (prices["Per week"].notes or "")


def test_audition_is_note_not_requirement():
    app = _offering().application
    assert app.requirements == []  # P1: audition is a separate event, not a join requirement
    assert app.notes is not None and "10 July 2026" in app.notes


def test_ages_levels_teachers_unset():
    o = _offering()
    assert o.age_range is None
    assert o.level == []
    assert o.teachers == []


def test_no_sessions_yields_nothing():
    assert cf._build_offerings("<p>Ballet Summer School coming soon</p>", URL) == []
