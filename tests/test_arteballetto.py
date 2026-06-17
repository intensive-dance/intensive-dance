from intensive_dance.scrapers import arteballetto as ab


def _post(pid, day, title, body):
    return {
        "id": pid,
        "date": f"{day}T00:00:00",
        "link": f"https://www.arteballetto.net/{pid}/",
        "title": {"rendered": title},
        "content": {"rendered": body},
    }


# 2026: dates + disciplines + faculty in prose "Name … (affiliation)".
P2026 = _post(
    1,
    "2026-05-17",
    "19° Summer Course in Sicily",
    "19° SUMMER COURSE IN SICILY – 6/11 Luglio2026 – Tania Fairbairn-Della Valle classico e "
    "repertorio femminile (International ballet teacher) Mikhail Soloviev classico e repertorio "
    "maschile ( PNSD – Cannes) Katharina Furst contemporaneo ( Iwanson – Munich) Il prestigioso "
    "Summer Course. La suddivisione delle classi in Principianti, Intermedio e Avanzato.",
)
# 2025: dash faculty list, disciplines NOT stated; an affiliation says "Contemporary Dance School".
P2025 = _post(
    2,
    "2025-06-12",
    "18° Summer Course in Sicily",
    "Dal 7 al 12 Luglio 2025 18° Summer Course in Sicily Ospiti Maestri Internazionali: "
    "– PATRICK ARMAND – Direttore Wiener Staatsoper Ballettakademie – SANDRA ASENSI – Conservatorio "
    "Fortea di Madrid – BAPTISTE BOURGOUGNON – Direttore London Contemporary Dance School A fine "
    "Corso verranno assegnate BORSE DI STUDIO.",
)
# A registration-form post that references an edition but isn't one → must be dropped.
PFORM = _post(
    3,
    "2023-06-27",
    "Clicca qui per scaricare il modulo di partecipazione al 16° Summer Course",
    "Per partecipare scaricare la scheda.",
)
# Thin past edition: date only in the title, no faculty/disciplines in the body.
P2021 = _post(
    4,
    "2021-06-02",
    "14′ Summer Course in Sicily – 26/31 Luglio 2021",
    "Borse di studio per E.N.B.S. e CSB di Londra.",
)


def _by_id(posts):
    return {o.id: o for o in ab._build_offerings(posts)}


def test_editions_kept_form_post_dropped():
    out = _by_id([P2026, P2025, PFORM, P2021])
    assert set(out) == {
        "arteballetto/2026",
        "arteballetto/2025",
        "arteballetto/2021",
    }


def test_dates_from_body_and_from_title_only():
    out = _by_id([P2026, P2021])
    o26 = out["arteballetto/2026"]
    assert o26.schedule.start is not None and o26.schedule.end is not None
    assert (o26.schedule.start.isoformat(), o26.schedule.end.isoformat()) == (
        "2026-07-06",
        "2026-07-11",
    )
    o21 = out["arteballetto/2021"]  # date lives only in the title
    assert o21.schedule.start is not None
    assert o21.schedule.start.isoformat() == "2021-07-26"


def test_genres_italian_only_no_affiliation_leak():
    out = _by_id([P2026, P2025])
    assert out["arteballetto/2026"].genres == ["classical", "contemporary", "repertoire"]
    # "London Contemporary Dance School" must NOT leak a contemporary genre (P3).
    assert out["arteballetto/2025"].genres == ["classical"]


def test_levels_when_stated_else_empty():
    out = _by_id([P2026, P2025])
    assert out["arteballetto/2026"].level == ["beginner", "intermediate", "advanced"]
    assert out["arteballetto/2025"].level == []


def test_teachers_prose_and_dash_names_only():
    out = _by_id([P2026, P2025])
    assert [t.name for t in out["arteballetto/2026"].teachers] == [
        "Tania Fairbairn-Della Valle",
        "Mikhail Soloviev",
        "Katharina Furst",
    ]
    # ALL-CAPS dash names are title-cased; affiliation prose is not kept.
    assert [t.name for t in out["arteballetto/2025"].teachers] == [
        "Patrick Armand",
        "Sandra Asensi",
        "Baptiste Bourgougnon",
    ]


def test_thin_edition_defaults_classical_no_teachers():
    o = _by_id([P2021])["arteballetto/2021"]
    assert o.genres == ["classical"]
    assert o.teachers == []
    assert o.location is not None and o.location.city == "Catania"
    assert o.prices == []  # never stated
