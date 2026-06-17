from intensive_dance.scrapers import dam_danza_torino as dam


def _post(title, body):
    slug = title.lower().replace(" ", "-")
    return {
        "link": f"https://www.damdanzatorino.it/{slug}/",
        "title": {"rendered": title},
        "content": {"rendered": body},
    }


BARDO = _post(
    "Dam – Summer Dance Intensive Bardonecchia 2026",
    "Summer Dance Intensive 2026 – BARDONECCHIA XVII EDIZIONE – APERTO A TUTTI 23 – 29 Agosto 2026. "
    "Discipline: DANZA CLASSICA e NEOCLASSICA, PUNTE e REPERTORIO, DANZA DI CARATTERE, DANZA "
    "CONTEMPORANEA, metodologia PBT, Hip Hop, Musical. Aperto a bambini e ragazzi dai 7 ai 23 anni.",
)
TORINO = _post(
    "Dam – Torino Danza Estate – Stage Intensivo 2026",
    "STAGE INTENSIVO di DANZA CLASSICA E CONTEMPORANEA dal 15 Giugno al 17 Luglio 2026. Discipline: "
    "TECNICA CLASSICA, PUNTE E REPERTORIO, CARATTERE, DANZA CONTEMPORANEA, FISIOTECNICA. APERTO A "
    "TUTTI: bambini dai 6 agli 11 anni, ragazzi dai 12 anni in su. Prima settimana (15-19 Giugno "
    "2026) Seconda settimana (22-26 Giugno 2026) Terza settimana (29 Giugno - 3 Luglio 2026) "
    "Quarta settimana (6-10 Luglio 2026) Quinta settimana (13-17 Luglio 2026).",
)
# Non-canonical duplicate (same year/program) and an out-of-scope post → both dropped.
SOLDOUT = _post(
    "Sold Out – Summer Dance Intensive Bardonecchia 2026",
    "23 – 29 Agosto 2026 tutto esaurito.",
)
GIFT = _post("Bardonecchia Gift Card", "Regala uno stage. 23 – 29 Agosto 2026.")


def _by_id(posts):
    return {o.id: o for o in dam._build_offerings(posts)}


def test_two_programs_canonical_only_deduped():
    out = _by_id([BARDO, TORINO, SOLDOUT, GIFT])
    assert set(out) == {
        "dam-danza-torino/bardonecchia-2026",
        "dam-danza-torino/torino-estate-2026",
    }  # Sold-Out dupe and Gift Card are dropped


def test_bardonecchia_dates_genres_ages():
    o = _by_id([BARDO])["dam-danza-torino/bardonecchia-2026"]
    assert o.schedule.start is not None and o.schedule.end is not None
    assert (o.schedule.start.isoformat(), o.schedule.end.isoformat()) == (
        "2026-08-23",
        "2026-08-29",
    )
    # ballet genres kept, Hip Hop / Musical dropped
    assert o.genres == [
        "neoclassical",
        "classical",
        "pointe",
        "contemporary",
        "repertoire",
        "character",
    ]
    assert o.age_range == {"min": 7, "max": 23}
    assert o.location is not None and o.location.city == "Bardonecchia"


def test_torino_two_month_span_and_weekly_sessions():
    o = _by_id([TORINO])["dam-danza-torino/torino-estate-2026"]
    assert (o.schedule.start.isoformat(), o.schedule.end.isoformat()) == (
        "2026-06-15",
        "2026-07-17",
    )
    weeks = [(s.start.isoformat(), s.end.isoformat()) for s in o.schedule.sessions]
    assert weeks == [
        ("2026-06-15", "2026-06-19"),
        ("2026-06-22", "2026-06-26"),
        ("2026-06-29", "2026-07-03"),  # cross-month week
        ("2026-07-06", "2026-07-10"),
        ("2026-07-13", "2026-07-17"),
    ]
    assert o.age_range == {"min": 6}  # open top ("dai 12 anni in su")


def test_no_prices_or_teachers_stated():
    o = _by_id([BARDO])["dam-danza-torino/bardonecchia-2026"]
    assert o.prices == []
    assert o.teachers == []  # hub lists "last edition" faculty — not attributed
