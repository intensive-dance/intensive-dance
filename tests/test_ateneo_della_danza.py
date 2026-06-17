from intensive_dance.models import VideoReq
from intensive_dance.scrapers import ateneo_della_danza as ad

URL = "https://www.ateneodelladanza.it/intensive-summer-school/"

# Trimmed Elementor markup mirroring the live page: prose with dates/curriculum/
# prices, plus faculty image-box widgets (h3 name + p "affiliation <br> disciplines").
HTML = """
<div class="elementor-widget-container">
  <p>Intensive Summer School dal 4 al 13 Luglio 2026, giunto alla 16° edizione.
  Lezioni di danza classica, tecnica di punte, tecnica maschile, repertorio,
  carattere, danza contemporanea, sbarra a terra e fisiotecnica. Per partecipare
  è necessario sostenere una pre-selezione video.</p>
  <h2>FACULTY</h2>
  <div class="elementor-image-box-content">
    <h3 class="elementor-image-box-title">Laura Ricci</h3>
    <p class="elementor-image-box-description">Ateneo della Danza <br>Danza Classica, Tecnica di Punte, Flamenco</p>
  </div>
  <div class="elementor-image-box-content">
    <h3 class="elementor-image-box-title">Davide Di Pretoro</h3>
    <p class="elementor-image-box-description">Assistente Wayne McGregor | Maitre Teatro dell'Opera di Roma <br>Danza Contemporanea</p>
  </div>
  <h2>Costi</h2>
  <h3>quota d'iscrizione</h3><h3>€700</h3><h3>€600</h3><p>se prenoti entro il 15/05</p>
  <h3>Alloggio</h3><h3>€540</h3>
  <h3>Pasti</h3><h3>€295</h3>
  <h3>Biglietti spettacoli</h3><h3>€15</h3>
  <h3>Caparra</h3><h3>€300</h3>
</div>
"""


def _offering():
    out = ad._build_offerings(HTML, URL)
    assert len(out) == 1
    return out[0]


def test_dates_and_title_year_stamped():
    o = _offering()
    assert o.id == "ateneo-della-danza/2026"
    assert o.title == "Intensive Summer School 2026"
    assert o.schedule.start is not None and o.schedule.end is not None
    assert (o.schedule.start.isoformat(), o.schedule.end.isoformat()) == (
        "2026-07-04",
        "2026-07-13",
    )


def test_genres_italian_curriculum():
    assert _offering().genres == ["classical", "pointe", "contemporary", "repertoire", "character"]


def test_ages_and_levels_unset():
    o = _offering()
    assert o.age_range is None
    assert o.level == []


def test_faculty_name_affiliation_role():
    teachers = {t.name: t for t in _offering().teachers}
    assert set(teachers) == {"Laura Ricci", "Davide Di Pretoro"}
    laura = teachers["Laura Ricci"]
    assert laura.role == "Danza Classica, Tecnica di Punte, Flamenco"
    assert laura.affiliations[0].organization == "Ateneo della Danza"
    # multi-part affiliation: source "|" is normalised, last line is the role.
    davide = teachers["Davide Di Pretoro"]
    assert davide.role == "Danza Contemporanea"
    assert (
        davide.affiliations[0].organization
        == "Assistente Wayne McGregor, Maitre Teatro dell'Opera di Roma"
    )


def test_prices_participant_fees_only():
    prices = {(p.amount, tuple(p.includes)) for p in _offering().prices}
    assert prices == {
        (700.0, ("tuition",)),
        (600.0, ("tuition",)),
        (540.0, ("accommodation",)),
        (295.0, ("meals",)),
    }  # show tickets (€15) and the deposit (€300) are NOT participant fees


def test_application_video_preselection():
    app = _offering().application
    assert len(app.requirements) == 1
    req = app.requirements[0]
    assert isinstance(req, VideoReq) and req.specificity == "unspecific"
    assert app.status is None  # not stated


def test_no_dates_yields_nothing():
    assert ad._build_offerings("<p>Intensive Summer School coming soon</p>", URL) == []
