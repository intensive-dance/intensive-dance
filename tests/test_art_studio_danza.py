from intensive_dance.scrapers import art_studio_danza as asd

URL = "https://artstudiodanza.it/29-stage-internazionale-del-lago-di-garda/"
TITLE = "29° Stage Internazionale del Lago di Garda"

HTML = """
<div>
  <p>29° Stage Internazionale del Lago di Garda dal 18 al 26 Luglio 2026 Salò (Bs).
  Ogni giorno: Pilates, sbarra a terra, tecnica accademica, repertorio, virtuosismi,
  punte, danza contemporanea e modern, composizione coreografica.</p>
  <div class="elementor-widget docente-title"><div class="elementor-widget-container">
    <p>JAROSLAV<br />SLAVICKÝ</p></div></div>
  <div class="elementor-widget docente-desc"><div class="elementor-widget-container">
    <p>Former Artistic Director <strong>Conservatory of Prague</strong></p></div></div>
  <div class="elementor-widget docente-desc"><div class="elementor-widget-container">
    <p>Tecnica Bournonville e composizione coreografica</p></div></div>
  <div class="elementor-widget docente-title"><div class="elementor-widget-container">
    <p>Fethon Miozzi</p></div></div>
  <div class="elementor-widget docente-desc"><div class="elementor-widget-container">
    <p>Docente Accademia Vaganova San Pietroburgo</p></div></div>
  <p>Hotel: Camera doppia / tripla / quadrupla €65,00 a persona al giorno Mezza pensione.</p>
  <p>Prezzi: Iscrizione €650,00 Tutor €250,00. Gala: Platea €20 Bambini €10.</p>
</div>
"""


def _offering():
    out = asd._build_offerings(HTML, URL, TITLE)
    assert len(out) == 1
    return out[0]


def test_dates_title_genres():
    o = _offering()
    assert o.id == "art-studio-danza/2026"
    assert o.title == "29° Stage Internazionale del Lago di Garda"
    assert o.schedule.start is not None and o.schedule.end is not None
    assert (o.schedule.start.isoformat(), o.schedule.end.isoformat()) == (
        "2026-07-18",
        "2026-07-26",
    )
    assert o.genres == ["classical", "pointe", "contemporary", "repertoire"]


def test_teachers_interleaved_title_desc():
    teachers = {t.name: t.role for t in _offering().teachers}
    assert set(teachers) == {"Jaroslav Slavický", "Fethon Miozzi"}  # ALL-CAPS name title-cased
    assert teachers["Jaroslav Slavický"] == (
        "Former Artistic Director Conservatory of Prague — Tecnica Bournonville e composizione coreografica"
    )


def test_prices_stage_and_lodging_only():
    prices = {(p.amount, tuple(p.includes)) for p in _offering().prices}
    assert prices == {
        (650.0, ("tuition",)),
        (65.0, ("accommodation", "meals")),
    }  # tutor / gala tickets are not the stage's own fee


def test_stage_slug_matches_summer_not_competition():
    assert asd._STAGE_SLUG.match("29-stage-internazionale-del-lago-di-garda")
    assert asd._STAGE_SLUG.match("24-stage-estivo-di-danza")
    assert not asd._STAGE_SLUG.match("winter-festival-2026")
    assert not asd._STAGE_SLUG.match("falling-leaves-concorso-di-danza")


def test_no_dates_yields_nothing():
    assert asd._build_offerings("<p>Stage coming soon</p>", URL, TITLE) == []
