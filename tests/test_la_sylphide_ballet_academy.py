from intensive_dance.scrapers import la_sylphide_ballet_academy as ls


def _page(slug, body):
    return {
        "slug": slug,
        "link": f"https://baletcopii.com/{slug}/",
        "title": {"rendered": slug},
        "content": {"rendered": body},
    }


# Current edition: header year trails the day span ("10-29 … Iulie 2024"), full
# curriculum, 3 age tiers, a stated deadline. The faculty bio after "Profesori"
# mentions "neoclasic"/"contemporane" — these must NOT leak into genres.
P2024 = _page(
    "summer-school",
    "<h2>LA SYLPHIDE SUMMER INTENSIVE 10-29 Iulie 2024</h2>"
    "<p>&Icirc;n fiecare an, &icirc;n cadrul La Sylphide Summer School intensiv... "
    "Vom avea 3 grupe de v&acirc;rst&abreve;: Age 1: 8 &#8211; 10 ani Age 2: 11 &#8211; 12 ani "
    "Age 3: 13 &#8211; 16 ani. Programul include: Balet, Dans modern, Repertoriu, Acro, "
    "Dans contemporan, Dans de caracter, Poante, Flamenco. "
    "&Icirc;nscrierea pentru Summer School se face online p&acirc;n&abreve; pe data de 25.06.2024 "
    "sau prin email c&abreve;tre office@baletcopii.com.</p>"
    "<p>Profesori invita&#539;i: Muriel Hall&eacute; &#8211; Fran&#539;a, fost&abreve; solist&abreve;, "
    "a dansat roluri clasice &#537;i contemporane &#537;i neoclasic.</p>",
)

# Past edition: header year leads ("Intensive 2021 5 – 24 Iulie"), no deadline,
# slimmer curriculum (no contemporary).
P2021 = _page(
    "summer-school-2021",
    "<h2>Summer School Intensive 2021 5 &#8211; 24 Iulie</h2>"
    "<p>&Icirc;n fiecare an... Vom avea 3 grupe de v&acirc;rst&abreve;: Age 1: 8 &#8211; 11 ani "
    "Age 2: 12 &#8211; 13 ani Age 3: 14 &#8211; 17 ani. Programul include: Balet, Repertoriu, "
    "Poante. &Icirc;nscrierea se face online.</p>",
)

# A look-alike with no parseable date header → dropped (returns None).
PNODATE = _page(
    "summer-school-old",
    "<p>&Icirc;n fiecare an organiz&abreve;m cursuri de var&abreve;.</p>",
)


def _by_id(pages):
    return {o.id: o for o in ls._build_offerings(pages)}


def test_editions_built_undated_dropped():
    out = _by_id([P2024, P2021, PNODATE])
    assert set(out) == {
        "la-sylphide-ballet-academy/2024",
        "la-sylphide-ballet-academy/2021",
    }


def test_dates_both_header_shapes():
    out = _by_id([P2024, P2021])
    o24 = out["la-sylphide-ballet-academy/2024"]
    assert o24.schedule.start is not None and o24.schedule.end is not None
    assert (o24.schedule.start.isoformat(), o24.schedule.end.isoformat()) == (
        "2024-07-10",
        "2024-07-29",
    )
    o21 = out["la-sylphide-ballet-academy/2021"]
    assert o21.schedule.start is not None and o21.schedule.end is not None
    assert (o21.schedule.start.isoformat(), o21.schedule.end.isoformat()) == (
        "2021-07-05",
        "2021-07-24",
    )


def test_genres_from_program_no_bio_leak():
    o = _by_id([P2024])["la-sylphide-ballet-academy/2024"]
    # contemporary IS taught (in the curriculum); neoclassical is only in the
    # teacher bio after "Profesori" and must not leak.
    assert o.genres == ["classical", "pointe", "repertoire", "character", "contemporary"]
    assert "neoclassical" not in o.genres
    assert _by_id([P2021])["la-sylphide-ballet-academy/2021"].genres == [
        "classical",
        "pointe",
        "repertoire",
    ]


def test_age_tiers_to_sessions_and_overall_range():
    o = _by_id([P2024])["la-sylphide-ballet-academy/2024"]
    assert o.age_range == {"min": 8, "max": 16}
    assert len(o.schedule.sessions) == 3
    s1 = o.schedule.sessions[0]
    assert s1.age_range == {"min": 8, "max": 10}
    assert s1.gender == "both"
    assert s1.start is not None and s1.start.isoformat() == "2024-07-10"


def test_application_deadline_and_unset_fields():
    out = _by_id([P2024, P2021])
    o24 = out["la-sylphide-ballet-academy/2024"]
    assert o24.application.deadline is not None
    assert o24.application.deadline.isoformat() == "2024-06-25"
    assert o24.application.requirements == []  # no audition material stated
    assert o24.prices == []  # fees never published
    assert o24.level == []
    assert o24.teachers == []
    assert o24.location is not None and o24.location.city == "Bucharest"
    # No deadline stated for 2021 → None, but still emitted.
    assert out["la-sylphide-ballet-academy/2021"].application.deadline is None
