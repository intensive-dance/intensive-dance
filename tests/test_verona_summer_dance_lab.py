from datetime import date

from intensive_dance.scrapers import verona_summer_dance_lab as v

# The proxy serves the Italian render by default; the page is bilingual. Mirrors
# the live Wix body (zero-width spaces, discipline labels split across lines, the
# orphan bio between two teachers, the missing price figure).
CONTENT_IT = """
<body>
<nav>HOME DOCENTI CORSI ALLOGGIO TARIFFE</nav>
<h1>Verona Summer Dance Lab</h1>
<p>-Quarta Edizione-</p>
<p>3-8 Agosto, 2026</p>
<h2>Docenti Ospiti</h2>
<p>Linda Gelinas<br>CLASSICO &amp; REPERTORIO<br>
Docente alla Juilliard School, co-direttrice al Metropolitan Opera Ballet.<br>Scopri di più<br>
Laureato alla Juilliard School classe 2021, ora a Staatstheater Kassel.</p>
<p>Barry Gans<br>CONTEMPORANEO, REPERTORIO &amp; LAB<br>Laureato alla Juilliard School.<br>Scopri di più</p>
<p>Mario Manara<br>CONTEMPORANEO, REPERTORIO<br>&amp; LAB<br>Laureato alla Rambert School.<br>Scopri di più</p>
<p>Sarah Pippin<br>CONTEMPORANEO, REPERTORIO<br>&amp; LAB<br>Laureata alla Juilliard School.<br>Scopri di più</p>
<p>6 giorni, 5 corsi, 4 docenti esclusivi presso l'Educandato Statale agli Angeli, Verona.</p>
<p>CLASSICO<br>CONTEMPORNEO<br>REPERTORIO<br>CLASSICO<br>REPERTORIO CONTEMPORANEO<br>LABORATORIO COREOGRAFICO</p>
<p>I gruppi A e B (Avanzato e Intermedio) verranno assegnati dopo la registrazione.</p>
<p>Le iscrizioni chiudono a raggiungimento della capienza, o non oltre il 5 Luglio.</p>
<p>Età consentita: dai 14 ai 30 anni. Lo stage è rivolto a chi studia regolarmente danza (no principianti).</p>
<p>Educandato Statale agli Angeli, Via Cesare Battisti 8, 37122 Verona VR, Italia</p>
</body>
"""


def _build(html=CONTENT_IT):
    return v._build_offerings(html, date(2026, 6, 17))


def test_single_offering_dates_italian_order():
    [o] = _build()
    assert o.id == "verona-summer-dance-lab/2026"
    assert o.title == "Verona Summer Dance Lab 2026"
    assert o.schedule.start == date(2026, 8, 3)
    assert o.schedule.end == date(2026, 8, 8)
    assert o.application.deadline == date(2026, 7, 5)


def test_genres_levels_ages():
    [o] = _build()
    assert o.genres == ["classical", "contemporary", "repertoire"]
    assert o.level == ["intermediate", "advanced"]
    assert o.age_range == {"min": 14, "max": 30}


def test_teachers_names_only_no_orphan_bio_or_headings():
    [o] = _build()
    assert [t.name for t in o.teachers] == [
        "Linda Gelinas",
        "Barry Gans",
        "Mario Manara",
        "Sarah Pippin",
    ]
    # "Dance Lab" (the hero heading) and "Scopri di più" must not be teachers.
    assert all(t.role is None for t in o.teachers)


def test_no_price_invented():
    # the tuition figure is a Wix widget absent from the HTML — never invented.
    [o] = _build()
    assert o.prices == []


def test_location():
    [o] = _build()
    assert o.location is not None
    assert o.location.venue == "Educandato Statale agli Angeli"
    assert o.location.city == "Verona"


def test_english_render_parses_identically():
    # if the proxy flips to the English render, dates/ages must still parse.
    english = (
        CONTENT_IT.replace("3-8 Agosto, 2026", "August 3-8, 2026")
        .replace("Età consentita: dai 14 ai 30 anni", "Age allowed: from 14 to 30 years old")
        .replace("non oltre il 5 Luglio", "no later than July 5th")
    )
    [o] = _build(english)
    assert o.schedule.start == date(2026, 8, 3)
    assert o.age_range == {"min": 14, "max": 30}
    assert o.application.deadline == date(2026, 7, 5)
