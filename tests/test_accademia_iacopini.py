import base64
import urllib.parse
from datetime import date

from intensive_dance import wp
from intensive_dance.scrapers import accademia_iacopini as ia

# The fee table ships as a base64-encoded (of url-quoted HTML) `[vc_raw_html]`
# card grid — one `.quote-card` per variant. Build it the way WPBakery stores it.
FEE_HTML = """
<div class="quote-wrapper">
  <div class="quote-card"><div class="quote-head">INdanza (Stage)</div>
    <div class="quote-grid--vals"><span class="cell">€ 750,00</span><span class="cell">€ 350,00</span><span class="cell">€ 400,00</span></div>
    <div class="quote-band">Early booking entro 30 aprile 2026: - € 100 sul totale: € 650,00</div></div>
  <div class="quote-card"><div class="quote-head">Percorso di Perfezionamento INdanza</div>
    <div class="quote-band">Quota Percorso Unico: € 450,00</div>
    <div class="quote-band">Quota Integrativa (per chi partecipa a INdanza): € 250,00</div></div>
  <div class="quote-card"><div class="quote-head">INdanza Kids</div>
    <div class="quote-grid--vals"><span class="cell">€ 300,00</span><span class="cell">€ 150,00</span><span class="cell">€ 150,00</span></div></div>
</div>
"""
_FEE_B64 = base64.b64encode(urllib.parse.quote(FEE_HTML).encode()).decode()

# Raw Jupiter/WPBakery shortcodes (no rendered <h*> headings): a date title, the
# faculty Name/role pairs bounded by the intro and the next section heading, the
# three variant age sentences, and the encoded fee table.
CONTENT = f"""
[mk_fancy_title]&#8220;IN&#8221; DANZA 5° Edizione[/mk_fancy_title]
[mk_fancy_title]26 Luglio – 1 Agosto 2026 Chianciano Terme Masterclass | Private Coaching | Gala[/mk_fancy_title]
[vc_column_text]Il percorso sarà guidato da docenti e direttori internazionali.[/vc_column_text]
[vc_column_text]Pino Alosa[/vc_column_text]
[vc_column_text]Ballet Master presso il Wiener Staatsballett[/vc_column_text]
[vc_column_text]Badley Shelver[/vc_column_text]
[vc_column_text]Docente Joffrey jazz e contemporary trainee program[/vc_column_text]
[mk_fancy_title]&#8220;IN DANZA&#8221; 5° Edizione[/mk_fancy_title]
[vc_column_text]Possono accedere a INdanza gli allievi di età compresa tra gli 11 e i 22 anni di età. Gli allievi saranno divisi in due classi: Intermedio e Avanzato.[/vc_column_text]
[vc_column_text]Per il Percorso di Perfezionamento INdanza (percorso unico) gli allievi di età compresa tra i 16 e i 22 anni di età.[/vc_column_text]
[vc_column_text]Per INdanza Kids gli allievi di età compresa tra gli 8 e i 10 anni.[/vc_column_text]
[mk_fancy_title]Quote di partecipazione[/mk_fancy_title]
[vc_raw_html]{_FEE_B64}[/vc_raw_html]
"""

POST = {
    "title": {"rendered": "&#8220;IN&#8221; DANZA 5° Edizione"},
    "link": "https://accademiaiacopini.it/in_danza_5_edizione/",
    "content": {"rendered": CONTENT},
}


def _build():
    return ia._build_offerings([POST], date(2026, 6, 17))


def test_unwrap_json_viewer_plain_wrapped_post():
    body = (
        '<html><body><pre>{"id":3853,"slug":"in_danza_5_edizione"}</pre><div></div></body></html>'
    )
    assert wp.unwrap_json_viewer(body) == {"id": 3853, "slug": "in_danza_5_edizione"}


def test_one_offering_per_variant():
    assert [o.id for o in _build()] == [
        "accademia-iacopini/2026-kids",
        "accademia-iacopini/2026-perfezionamento",
        "accademia-iacopini/2026-stage",
    ]


def test_stage_dates_ages_levels_and_fee():
    stage = next(o for o in _build() if o.id.endswith("stage"))
    assert stage.schedule.start == date(2026, 7, 26)
    assert stage.schedule.end == date(2026, 8, 1)
    assert stage.age_range == {"min": 11, "max": 22}
    assert stage.level == ["intermediate", "advanced"]
    assert [p.amount for p in stage.prices] == [750.0]
    assert "650" in (stage.prices[0].notes or "")


def test_perfezionamento_two_fees_and_age():
    perf = next(o for o in _build() if o.id.endswith("perfezionamento"))
    assert perf.age_range == {"min": 16, "max": 22}
    assert [p.amount for p in perf.prices] == [450.0, 250.0]
    assert perf.level == []  # the source states no level for this variant


def test_kids_age_fee_and_no_named_teachers():
    kids = next(o for o in _build() if o.id.endswith("kids"))
    assert kids.age_range == {"min": 8, "max": 10}
    assert [p.amount for p in kids.prices] == [300.0]
    assert kids.teachers == []


def test_genres_from_faculty_specialties_not_blurb():
    stage = next(o for o in _build() if o.id.endswith("stage"))
    # classical (Wiener Staatsballett ballet master) + contemporary (Joffrey).
    assert stage.genres == ["classical", "contemporary"]
    names = {t.name for t in stage.teachers}
    assert names == {"Pino Alosa", "Badley Shelver"}
    assert all(t.role for t in stage.teachers)
