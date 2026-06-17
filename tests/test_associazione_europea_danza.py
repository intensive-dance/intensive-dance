from datetime import date

from intensive_dance.scrapers import associazione_europea_danza as aed

# The site's REST JSON comes back inside Chromium's JSON viewer (`<pre>`,
# HTML-escaped) with Cloudflare's email-protection script having injected a real
# `<a class="__cf_email__">` tag into the displayed email — corrupting the JSON.
# Legit angle-brackets are escaped (`&lt;`), so only the injection is a real tag.
VIEWER = """<html><body><pre>{"id":9401,"title":{"rendered":"Summer Dance School \
Livorno Italy"},"content":{"rendered":"&lt;p&gt;e-mail: <a href="/cdn-cgi/l/email-protection" \
class="__cf_email__" data-cfemail="abc">[email&#160;protected]</a> &amp;amp; phone&lt;/p&gt;\
"}}</pre></body></html>"""

# The live post shape: two adjacent <h4> week headers (dates live here), then one
# flat paragraph stream. The Classic detail starts at an in-body "Classic" week
# line; a shared tail (Class location, dress code) follows. The dress-code line
# names "contemporary classes" — it must NOT leak a contemporary genre into the
# Classic offering, so genres are matched per week before the tail.
CONTENT = """
<h4>Summer Dance School Livorno Italy“Contemporary” week from the 20 July until the 25 July 2026</h4>
<h4>“Classic” week from the 27 July until 1 August 2026</h4>
<p>Summer dance school. By the sea, the best teachers</p>
<p>APPLICATIONS ARE OPEN</p>
<p>CONTEMPORARY WEEK<br>IMPROVISATION, REPERTORY<br>
<a href="https://aed.dance/en/services-aed-dance/sanja-maier-hasagic/">SANJA MAIER HASAGIC</a><br>
<strong>Coordinator , teacher and ripetiteur CODARTS Rotterdam</strong><br>
CONTEMPORARY TECHNIQUE AND CONTEMPORARY REPERTORY<br>
<a href="https://aed.dance/en/services-aed-dance/neel-verdoorn-2/">NEEL VERDOORN</a><br>
<strong>Coreographer, teacher CODARTS Rotterdam</strong><br>age:&nbsp;14 years old and up</p>
<p>14,30-16,00 Contemporary technique<br>16,15-17,45 workshop<br>18,00-19,30 Improvisation and repertory</p>
<p>three classes one week 390 euro. A &#8364;150 deposit is required at the time of booking.<br>
The remaining &#8364;240 must be paid on site on the first day of classes.</p>
<p>“Classic” week from the 27 July until 1 August 2026</p>
<p>Classical Ballet – Pointe Technique &amp; Repertoire<br>
<a href="https://aed.dance/servizi-aed-dance/liane-mcrae/"><strong>LIANE MCRAE</strong></a><br>
<strong>Artistic Manager Foundation Programme The Royal Ballet School</strong></p>
<p><strong>NICOLA TRANAH</strong><br><strong>Royal Ballet, international teacher</strong></p>
<p>Age: 11–13 years (Group 1); 14 years and up (Group 2)</p>
<p>Group 1 and Group 2: three classes, one week – &#8364;390.<br>
A &#8364;150 deposit is required at the time of booking.</p>
<p>Schedule<br>Group 1<br>10:00–11:30 — Classical Ballet Technique<br>11:45–12:45 — Pointe Work<br>
Group 2<br>14:00–15:30 — Classical Ballet Technique<br>15:30–16:30 — Pointe Work</p>
<p>Class location: Via Masi 7, Livorno.</p>
<p>DRESS CODE<br>Socks for contemporary classes (first week), and ballet slippers and pointe shoes for classical classes.</p>
"""

POST = {
    "title": {"rendered": "Summer Dance School Livorno Italy"},
    "link": "https://aed.dance/en/workshop/summer-dance-school-livorno-italy/",
    "content": {"rendered": CONTENT},
}


def _build():
    return aed._build_offerings([POST], date(2026, 6, 17))


def test_unwrap_strips_cf_email_injection_and_parses():
    [record] = aed._unwrap(VIEWER)
    assert record["id"] == 9401
    # The CF anchor (its real `"` quotes would have broken json.loads) is gone,
    # while the escaped HTML in content survives as real markup with `&amp;`.
    assert "__cf_email__" not in record["content"]["rendered"]
    assert "&amp; phone" in record["content"]["rendered"]


def test_emits_one_offering_per_week():
    offers = _build()
    assert [o.id for o in offers] == [
        "associazione-europea-danza/2026-classic",
        "associazione-europea-danza/2026-contemporary",
    ]


def test_contemporary_week():
    contemporary = next(o for o in _build() if o.id.endswith("contemporary"))
    assert contemporary.genres == ["contemporary", "repertoire"]
    assert contemporary.age_range == {"min": 14, "max": None}
    assert contemporary.schedule.start == date(2026, 7, 20)
    assert contemporary.schedule.end == date(2026, 7, 25)
    # The €390 course fee, not the €150 deposit on the same line.
    assert [p.amount for p in contemporary.prices] == [390.0]
    assert {t.name for t in contemporary.teachers} == {"Sanja Maier Hasagic", "Neel Verdoorn"}


def test_classic_week_age_group_sessions():
    classic = next(o for o in _build() if o.id.endswith("classic"))
    assert classic.schedule.start == date(2026, 7, 27)
    assert classic.schedule.end == date(2026, 8, 1)
    assert classic.age_range == {"min": 11, "max": None}
    sessions = {s.label: s.age_range for s in classic.schedule.sessions}
    assert sessions == {
        "Group 1": {"min": 11, "max": 13},
        "Group 2": {"min": 14, "max": None},
    }


def test_classic_week_does_not_leak_contemporary_from_dress_code():
    # The shared dress-code tail mentions "contemporary classes"; it sits after
    # "Class location" and must be trimmed off before genre matching.
    classic = next(o for o in _build() if o.id.endswith("classic"))
    assert classic.genres == ["classical", "pointe", "repertoire"]
    assert "contemporary" not in classic.genres
    # McRae casing is preserved through title-casing the ALL-CAPS source name.
    assert any(t.name == "Liane McRae" for t in classic.teachers)


def test_dateless_promo_post_is_skipped():
    promo = {
        "title": {"rendered": "SUMMER SCHOOL un mese, i migliori docenti da tutto il mondo !"},
        "link": "https://aed.dance/stage-corso-estivo-danza/",
        "content": {"rendered": "<p>studia a luglio, corso estivo danza</p>"},
    }
    assert aed._build_offerings([promo], date(2026, 6, 17)) == []
