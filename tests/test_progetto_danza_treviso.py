from datetime import date

from intensive_dance.scrapers import progetto_danza_treviso as pdt

DETAIL = """
<div class="contentWrap">
  <h1>40° STAGE INTERNAZIONALE DI DANZA 2026</h1>
  <p>Dal 28.06.2026 al 11.07.2026</p>
  <p>ISCRIZIONI ENTRO IL 10 GIUGNO 2026</p>
  <h3>Insegnanti</h3>
  <p>Margarita Smirnova<br>Frédéric Olivieri<br>Vincent Chaillet</p>
  <h3>Come iscriversi</h3>
  <p>Sono disponibili tessere livello intermedio e livello avanzato.
     TESSERA OPEN LIVELLO BAMBINI (9-11 ANNI): Settimana € 400,00.</p>
  <p>QUOTE DI PARTECIPAZIONE:</p>
  <p>OPEN CARD 1 settimana € 650,00<br>OPEN CARD 2 settimane € 1.050,00<br>
     OPEN CARD BAMBINI DAL 28/6 AL 11/7 € 500,00<br>QUOTA DI ISCRIZIONE € 50,00</p>
  <p>SPECIALE PROMOZIONE 2026:</p>
  <p>Iscrivendoti ad almeno 2 corsi potrai frequentare un ulteriore corso a € 100,00</p>
</div>
"""

# The disciplines come only from the programme PDF; the genres must be read here,
# not from the HTML (which never names them).
PDF_TEXT = """
DANZA CLASSICA
MARGARITA SMIRNOVA Bambini / Avanzato / Repertorio
LUCIA GEPPI Intermedio / Punte
DANZA CONTEMPORANEA
DAMIANO ARTALE Intermedio / Avanzato
CONTEMPORARY URBAN
MARIO GLEZ
DANZA MODERNA
CLAUDIA ROSSI
MUSICAL
GIORGIO CAMANDONA
MARTINA FORIOSO Neo classico av.
"""

URL = "https://www.progettodanza.org/iniziative/40-stage-internazionale-di-danza-2026/"


def _build():
    return pdt._build_offerings(DETAIL, URL, PDF_TEXT, date(2026, 6, 17))


def test_emits_single_dated_offering():
    [o] = _build()
    assert o.id == "progetto-danza-treviso/2026"
    assert o.title == "40° Stage Internazionale di Danza 2026"
    assert o.schedule.start == date(2026, 6, 28)
    assert o.schedule.end == date(2026, 7, 11)
    assert o.application.deadline == date(2026, 6, 10)  # past, but kept (IDR-24)


def test_genres_from_pdf_programme_not_html():
    [o] = _build()
    # classical, contemporary (+urban), neoclassical, repertoire, pointe — in
    # table order; danza moderna / musical have no enum genre.
    assert o.genres == ["classical", "contemporary", "neoclassical", "repertoire", "pointe"]


def test_levels_and_open_topped_age():
    [o] = _build()
    assert o.level == ["intermediate", "advanced"]
    assert o.age_range == {"min": 9, "max": None}


def test_teachers_names_only():
    [o] = _build()
    assert [t.name for t in o.teachers] == [
        "Margarita Smirnova",
        "Frédéric Olivieri",
        "Vincent Chaillet",
    ]
    assert all(t.role is None for t in o.teachers)


def test_prices_block_and_registration_fee():
    [o] = _build()
    by_amount = {p.amount: p for p in o.prices}
    assert set(by_amount) == {650.0, 1050.0, 500.0, 50.0}
    # the €50 registration fee is not tuition; the €100 promo line below the
    # block is not part of QUOTE DI PARTECIPAZIONE and must not be picked up.
    assert by_amount[50.0].includes == []
    assert by_amount[650.0].includes == ["tuition"]
    assert 100.0 not in by_amount


def test_discovery_picks_latest_year_and_pdf():
    home = """
    <a href="/iniziative/39-stage-internazionale-di-danza-2025/">2025</a>
    <a href="/iniziative/40-stage-internazionale-di-danza-2026/">2026</a>
    <a href="/iniziative/23-concorso-internazionale-di-danza-2026/">concorso</a>
    """
    assert pdt._latest_stage_url(home) == URL
    detail = '<a href="/wp-content/files_mf/123PROGRAMMASTAGE2026.pdf">Scarica il programma</a>'
    pdf_url = pdt._programma_pdf_url(detail)
    assert pdf_url is not None and pdf_url.endswith("PROGRAMMASTAGE2026.pdf")
