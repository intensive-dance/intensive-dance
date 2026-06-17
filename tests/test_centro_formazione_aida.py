from intensive_dance.scrapers import centro_formazione_aida as cfa


def _post(title, body):
    return {
        "link": "https://www.centroformazioneaida.com/x/",
        "title": {"rendered": title},
        "content": {"rendered": body},
    }


CAMP = _post(
    "Ballet Summer Camp – dal 15 al 26 giugno 2026",
    "BALLET SUMMER CAMP. Stage estivo. Dal 15 al 26 giugno 2026. Discipline: Tecnica classica, "
    "Punte e repertorio, Tecnica maschile, Tecnica contemporanea, Sbarra a terra. SONO PREVISTI 3 "
    "LIVELLI: I livello 10/11 anni II livello 12/13 anni III livello 14/16 anni. SONO PREVISTE 2 "
    "SESSIONI: I SESSIONE dal 15 al 19 giugno 2026 II SESSIONE dal 22 al 26 giugno 2026. Saranno "
    "ritenute valide le iscrizioni pervenute entro il 3 giugno 2025. Periodo di prova per "
    "un'eventuale ammissione all'a.a. 2025/2026.",
)
# Out of scope (toddlers) — must be dropped by the title filter.
BABY = _post("Baby Summer Camp", "Dal 15 al 19 giugno 2026 per i piccolissimi.")


def _by_id(posts):
    return {o.id: o for o in cfa._build_offerings(posts)}


def test_only_ballet_camp_kept():
    out = _by_id([CAMP, BABY])
    assert set(out) == {"centro-formazione-aida/2026"}


def test_sessions_overall_genres_ages():
    o = _by_id([CAMP])["centro-formazione-aida/2026"]
    assert o.schedule.start is not None and o.schedule.end is not None
    assert (o.schedule.start.isoformat(), o.schedule.end.isoformat()) == (
        "2026-06-15",
        "2026-06-26",
    )
    weeks = [(s.start.isoformat(), s.end.isoformat()) for s in o.schedule.sessions]
    assert weeks == [("2026-06-15", "2026-06-19"), ("2026-06-22", "2026-06-26")]
    assert o.genres == ["classical", "pointe", "contemporary", "repertoire"]
    assert o.age_range == {"min": 10, "max": 16}
    assert o.level == []  # age tiers, not skill levels


def test_deadline_year_typo_corrected_to_course_year():
    app = _by_id([CAMP])["centro-formazione-aida/2026"].application
    assert app.deadline is not None
    assert app.deadline.isoformat() == "2026-06-03"  # source typo "3 giugno 2025" → course year
    assert app.requirements == []  # trial-for-admission is a note, not a requirement (P1)
    assert app.notes is not None and "trial" in app.notes.lower()
