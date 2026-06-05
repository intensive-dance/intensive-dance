"""Unit tests for the Accademia Teatro alla Scala scraper (custom CMS, IT).

These pin the fragile Italian-language parsing of the two summer programmes:
the one-week `schedule.sessions` (including the elided "dall'8" opener and the
year stated only on the last block of an "e"-joined run), the grade-group ages,
the prof/semi-prof level, the curriculum genres, the EUR fee with its canteen
`meals` include, and the single-vs-multiple deadline rule. Inline strings, no
network — `_build_*` and the helpers take text directly.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import NoneReq
from intensive_dance.scrapers import accademia_teatro_alla_scala as scala

# Condensed but faithful to the live "Stage estivi di danza" page.
_SUMMER = (
    "Stage estivi di danza In breve Durante l'estate il Dipartimento Danza propone "
    "stage settimanali rivolti a danzatori di livello professionale o semi-professionale. "
    "Prerequisiti Gruppo A: classi 1, 2 e 3 media. Gruppo B: dalla terza superiore "
    "fino ai 23 anni non compiuti al 10 luglio 2026 "
    "Durata Due stage settimanali: dal 29 giugno al 3 luglio e dal 6 al 10 luglio 2026 "
    "Costo di frequenza € 820 per ciascuna settimana (il costo comprende un pasto in "
    "mensa per tutti i giorni di lezione) "
    "Iscrizioni 2026 Entro il 7 giugno 2026 (possibili fino a esaurimento dei posti "
    "disponibili) Scarica la brochure "
    "Programma 7,5 ore di danza classico-accademica; 5 ore di repertorio/punta; "
    "3 ore di danza moderno-contemporanea; 2 ore di sbarra a terra."
)

# Condensed but faithful to the live "Stage di propedeutica alla danza" page.
_PROPEDEUTICA = (
    "Stage di propedeutica alla danza In breve Stage di propedeutica per bambini. "
    "Profilo partecipante Bambini tra i 7 e gli 11 anni che frequentano la primaria. "
    "Durata Stage settimanali: - dall'8 al 12 giugno 2026 - dal 15 al 19 giugno 2026 "
    "- dal 22 al 26 giugno 2026 - dal 31 agosto al 4 settembre 2026 "
    "Costo di frequenza € 390 a sessione "
    "Iscrizioni 2026 Entro il 22 maggio per le sessioni di giugno Entro il 10 luglio "
    "per la sessione di fine agosto Scarica la brochure "
    "Programma dello Stage Propedeutica alla danza classico-accademica Stretchtonic"
)


def test_summer_sessions_two_weeks_year_backfilled():
    sessions = scala._sessions(_SUMMER)
    # The first block carries no year (stated only after the second); it must
    # back-fill to 2026, and the cross-month start month must be kept.
    assert [(s.start, s.end) for s in sessions] == [
        (date(2026, 6, 29), date(2026, 7, 3)),
        (date(2026, 7, 6), date(2026, 7, 10)),
    ]
    assert sessions[0].notes == "29 giugno–3 luglio 2026"
    assert sessions[1].notes == "6–10 luglio 2026"


def test_propedeutica_sessions_handle_elided_opener():
    sessions = scala._sessions(_PROPEDEUTICA)
    assert [(s.start, s.end) for s in sessions] == [
        (date(2026, 6, 8), date(2026, 6, 12)),  # "dall'8" elision
        (date(2026, 6, 15), date(2026, 6, 19)),
        (date(2026, 6, 22), date(2026, 6, 26)),
        (date(2026, 8, 31), date(2026, 9, 4)),
    ]


def test_age_range_upper_bound_vs_band():
    assert scala._age_range(_SUMMER) == {"max": 23}  # "fino ai 23 anni"
    assert scala._age_range(_PROPEDEUTICA) == {"min": 7, "max": 11}


def test_levels_professional_and_semi():
    assert scala._levels(_SUMMER) == ["professional", "pre-professional"]
    assert scala._levels(_PROPEDEUTICA) == []


def test_genres_keyed_off_curriculum():
    assert scala._genres(_SUMMER) == ["classical", "contemporary", "repertoire", "pointe"]


def test_prices_summer_includes_meals():
    prices = scala._prices(_SUMMER)
    assert len(prices) == 1
    assert prices[0].amount == 820.0
    assert prices[0].currency == "EUR"
    assert prices[0].includes == ["tuition", "meals"]


def test_prices_propedeutica_tuition_only():
    prices = scala._prices(_PROPEDEUTICA)
    assert prices[0].amount == 390.0
    assert prices[0].includes == ["tuition"]


def test_deadline_single_vs_multiple():
    # Summer states one dated deadline → set it.
    assert scala._deadline(_SUMMER) == date(2026, 6, 7)
    # Propedeutica's per-session deadlines carry no year here and aren't a single
    # programme deadline → leave null.
    assert scala._deadline(_PROPEDEUTICA) is None


def test_build_summer_offering():
    offering = scala._build_summer_stage(_SUMMER, scala.SUMMER_STAGE)
    assert offering is not None
    assert offering.id == "accademia-teatro-alla-scala/stage-estivi-di-danza-2026"
    assert offering.kind == "summer-school"
    assert offering.schedule.start == date(2026, 6, 29)
    assert offering.schedule.end == date(2026, 7, 10)
    assert offering.schedule.season == "2026"
    assert offering.location is not None
    assert offering.location.venue == "Via Campo Lodigiano, 2"
    assert offering.location.city == "Milan"
    assert offering.application.url == scala.APPLY_URL
    assert offering.application.requirements == [NoneReq()]


def test_build_propedeutica_offering_classical_only():
    offering = scala._build_propedeutica(_PROPEDEUTICA, scala.PROPEDEUTICA)
    assert offering is not None
    assert offering.id == "accademia-teatro-alla-scala/stage-di-propedeutica-alla-danza-2026"
    assert offering.genres == ["classical"]
    assert offering.level == []
    assert len(offering.schedule.sessions) == 4


def test_no_sessions_yields_no_offering():
    assert scala._build_summer_stage("Nessuna data qui.", scala.SUMMER_STAGE) is None
