from intensive_dance.scrapers import accademia_internazionale_coreutica as aic

# WPBakery body shape: a flat run of [vc_column_text] label/value blocks, names
# wrapped in <strong>, <br/> between them. Mirrors the live XXIV (2025) edition.
XXIV = """
[vc_row][vc_column][vc_column_text]<h2>CORSO INTERNAZIONALE ESTIVO XXIV EDIZIONE</h2>
Dal 21 al 26 Luglio 2025[/vc_column_text][vc_column_text]Corso Allievi: dai 10 ai 20 anni
[/vc_column_text][vc_column_text]Livelli: Elementare (dai 10 anni), Intermedio, Avanzato:
Danza classica (tecnica), Danza contemporanea (Tecnica Flying Low), Danza di carattere, PBT®
[/vc_column_text][vc_column_text]<h3>Docenti</h3>[/vc_column_text][vc_column_text]
<strong>Irene Cioni (Danza Contemporanea tecnica Flying Low)<br/></strong>
<strong>Chiara Prina (Danza Classica, PBT&#174;)</strong>[/vc_column_text]
[vc_column_text]Maestra accompagnatrice al pianoforte[/vc_column_text][vc_column_text]
Yoko Wakabayashi[/vc_column_text][vc_column_text]Audizione[/vc_column_text][vc_column_text]
Lo stage è valido come audizione per l’anno accademico 2025/2026[/vc_column_text]
[vc_column_text]SPETTACOLO – 26 Luglio 2025[/vc_column_text][vc_column_text]
Costo biglietti: Posto unico €12,00[/vc_column_text][vc_column_text]Costo del corso[/vc_column_text]
[vc_column_text]FORMULA 5 LEZIONI AL GIORNO € 500,00 FORMULA 2 LEZIONI AL GIORNO € 250,00
[/vc_column_text][vc_column_text]Scadenza iscrizioni: 12 luglio 2025[/vc_column_text]
[vc_column_text]Sede del corso[/vc_column_text][vc_column_text]Corso Estivo : Accademia
Internazionale Coreutica Via delle Ghiacciaie 1/3R Firenze. Spettacolo : Teatro l’Affratellamento
[/vc_column_text][/vc_column][/vc_row]
"""

# XXIII (2024): a two-month-style label is absent, but pointe + repertoire ARE in
# the curriculum, and an invited teacher carries a "Name: career bio (discipline)".
XXIII = """
[vc_column_text]CORSO INTERNAZIONALE ESTIVO XXIII EDIZIONE Dal 22 al 27 Luglio 2024[/vc_column_text]
[vc_column_text]Corso Allievi: dai 10 ai 20 anni[/vc_column_text][vc_column_text]
Livello Elementare, Danza classica (tecnica), Tecnica di Punta e Tecnica maschile,
Danza contemporanea (tecnica), Coaching Repertorio, Danza di carattere[/vc_column_text]
[vc_column_text]Docenti stabili[/vc_column_text][vc_column_text]
<strong>Eliane Mazzotti (Danza di carattere)</strong>[/vc_column_text]
[vc_column_text]Docenti invitati[/vc_column_text][vc_column_text]
<strong>Ivan Cavallari: Direttore Grands Ballets Canadiens Montreal,Canada. (Danza Classica tecnica Avanzato)</strong>
[/vc_column_text][vc_column_text]Costo del corso[/vc_column_text][vc_column_text]
FORMULA 5 LEZIONI AL GIORNO € 500,00[/vc_column_text]
"""


def _post(slug, title, content):
    link = f"https://www.accademiainternazionalecoreutica.org/{slug}/"
    return {"link": link, "title": {"rendered": title}, "content": {"rendered": content}}


def _by_id(offerings):
    return {o.id: o for o in offerings}


def test_two_editions_emitted_and_year_stamped():
    out = aic._build_offerings(
        [
            _post("xxiv", "Corso Internazionale Estivo XXIV Edizione", XXIV),
            _post("xxiii", "Concorso Internazionale Estivo XXIII Edizione", XXIII),
        ]
    )
    ids = _by_id(out)
    assert set(ids) == {
        "accademia-internazionale-coreutica/2025",
        "accademia-internazionale-coreutica/2024",
    }


def test_dates_ages_and_summer_season():
    o = _by_id(aic._build_offerings([_post("x", "Estivo XXIV", XXIV)]))[
        "accademia-internazionale-coreutica/2025"
    ]
    assert o.schedule.start is not None and o.schedule.end is not None
    assert o.schedule.start.isoformat() == "2025-07-21"
    assert o.schedule.end.isoformat() == "2025-07-26"
    assert o.schedule.season == "summer"
    assert o.age_range == {"min": 10, "max": 20}


def test_title_keeps_roman_numeral():
    o = aic._build_offerings([_post("x", "Estivo XXIV", XXIV)])[0]
    assert o.title == "Corso Internazionale Estivo XXIV Edizione"


def test_genres_scoped_to_curriculum_per_edition():
    out = _by_id(
        aic._build_offerings(
            [
                _post("xxiv", "Estivo XXIV", XXIV),
                _post("xxiii", "Estivo XXIII", XXIII),
            ]
        )
    )
    # XXIV teaches no pointe/repertoire; XXIII does.
    assert out["accademia-internazionale-coreutica/2025"].genres == [
        "classical",
        "contemporary",
        "character",
    ]
    assert out["accademia-internazionale-coreutica/2024"].genres == [
        "classical",
        "pointe",
        "contemporary",
        "repertoire",
        "character",
    ]


def test_levels_mapped():
    o = aic._build_offerings([_post("x", "Estivo XXIV", XXIV)])[0]
    assert o.level == ["beginner", "intermediate", "advanced"]


def test_prices_scoped_to_course_not_show_ticket():
    o = aic._build_offerings([_post("x", "Estivo XXIV", XXIV)])[0]
    amounts = sorted(p.amount for p in o.prices)
    assert amounts == [250.0, 500.0]  # the €12 show ticket is NOT a course fee
    assert all(p.currency == "EUR" and p.includes == ["tuition"] for p in o.prices)


def test_teachers_clean_and_invited_bio_split():
    out = _by_id(
        aic._build_offerings(
            [_post("xxiv", "Estivo XXIV", XXIV), _post("xxiii", "Estivo XXIII", XXIII)]
        )
    )
    names_25 = [t.name for t in out["accademia-internazionale-coreutica/2025"].teachers]
    assert names_25 == ["Irene Cioni", "Chiara Prina"]  # pianist excluded, no letter-spacing
    invited = out["accademia-internazionale-coreutica/2024"].teachers[-1]
    assert invited.name == "Ivan Cavallari"  # career bio after the colon is dropped from the name


def test_application_deadline_and_audition_note_not_requirements():
    o = aic._build_offerings([_post("x", "Estivo XXIV", XXIV)])[0]
    assert o.application.deadline is not None and o.application.notes is not None
    assert o.application.deadline.isoformat() == "2025-07-12"
    assert o.application.requirements == []  # P1: don't import academy-entry audition rules
    assert "audizione" in o.application.notes.lower()


def test_location_is_course_venue_not_show_venue():
    o = aic._build_offerings([_post("x", "Estivo XXIV", XXIV)])[0]
    assert o.location is not None and o.location.venue is not None
    assert o.location.city == "Florence"
    assert "Ghiacciaie" in o.location.venue
    assert "Affratellamento" not in o.location.venue  # show venue excluded


def test_non_summer_corso_post_skipped():
    winter = "[vc_column_text]Corso di Natale Dal 2 al 5 gennaio 2025[/vc_column_text]"
    assert aic._build_offerings([_post("natale", "Corso di Natale", winter)]) == []
