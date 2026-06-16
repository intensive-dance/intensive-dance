"""Unit tests for the Győri Balett — Dance Intensive scraper (offline, no network).

The fixtures mirror the real `content.rendered` of the 2025 EN page (SiteOrigin
Page Builder widgets, plain HTML) — including the per-track teacher anchors and
the dotted-time contemporary line — plus an undated edge page.
"""

from __future__ import annotations

from intensive_dance.models import NoneReq
from intensive_dance.scrapers import gyori_balett_dance_intensive as gyori

# Trimmed copy of the live 2025 EN page body: intro with the dated festival-independent
# range, the two workshop tracks (each with its teacher anchor + daily times — note the
# contemporary block uses dotted times "16.00 to 17.30"), per-track + combined HUF prices.
_RENDERED_2025 = """
<h2 class="widget-title">Grow, be inspired, be a part of it!</h2>
<div class="textwidget"><p><span>Join the intensive dance workshops organized within the
XX. Hungarian Dance Festival between 18 and 22 June 2025 in Győr! We welcome all participants
who wish to develop in classical ballet and contemporary dance by learning from foreign
teachers.</span></p></div>
<h2 class="widget-title">Guest teachers:</h2>
<div class="textwidget">
<p><span>Classical ballet by </span><span>Marcello Algeri<br /></span>
<span>Contemporary dance: </span><span>Jordan James Bridge</span></p>
<p><b>When?</b><span> 18-22 June<br /></span>
<b>Where?</b><span> Szabolcska Mihály Str. 5, Győr 9023 &#8211; Dance and Fine Arts Primary
School, Vocational High School and College &#8211; Ballet Hall</span></p>
<p><b>Classical ballet workshop: <a href="https://gyoribalett.hu/marcello-algeri-en/"
target="_blank" rel="noopener">Marcello Algeri</a><br /></b>
<span>Every day from 14:00 to 15:30<br /></span>
<span>10,000 HUF /hour<br /></span><span>40,000 HUF a 5-day PASS</span></p>
<p><span> </span><b>Contemporary dance workshop: <a href="https://gyoribalett.hu/jordan-james-bridge-en/"
target="_blank" rel="noopener">Jordan James Bridge</a><br /></b>
<span>Every day from 16.00 to 17.30<br /></span>
<span>10,000 HUF/hour<br /></span><span>40,000 HUF a 5-day PASS</span></p>
<p><span> </span><strong>Combined PASS for the 5 days:<br /></strong>
<span>80,000 HUF combined classical ballet and contemporary dance PASS for 5 days</span></p>
<p><span>Do you have a question? Feel free to write us! application@gyoribalett.hu</span></p>
</div>
"""

# A future edition page whose body has no stated date range yet (only a contact line) —
# the festival window must NEVER be borrowed, so this must emit nothing.
_RENDERED_UNDATED = """
<h2>Grow, be inspired, be a part of it!</h2>
<p>The Dance Intensive returns within the Hungarian Dance Festival in Győr.
Details coming soon — write to application@gyoribalett.hu.</p>
"""

URL = "https://gyoribalett.hu/dance-intensive-gyor-2025-en/"


def _offering(year: int = 2025, rendered: str = _RENDERED_2025):
    return gyori._build_offering(URL, year, rendered)


def test_dates_read_off_the_intensive_page_not_the_festival():
    o = _offering()
    assert o is not None
    assert o.id == "gyori-balett-dance-intensive/2025"
    assert o.schedule.season == "2025"
    assert o.schedule.start is not None and o.schedule.start.isoformat() == "2025-06-18"
    assert o.schedule.end is not None and o.schedule.end.isoformat() == "2025-06-22"
    assert o.schedule.timezone == "Europe/Budapest"


def test_undated_edition_emits_nothing():
    assert _offering(year=2026, rendered=_RENDERED_UNDATED) is None


def test_genres():
    o = _offering()
    assert o is not None
    assert set(o.genres) == {"classical", "contemporary"}


def test_location():
    o = _offering()
    assert o is not None and o.location is not None
    assert o.location.city == "Győr"
    assert o.location.country == "HU"
    assert o.location.venue is not None
    assert "Ballet Hall" in o.location.venue
    assert "Szabolcska" in o.location.venue


def test_one_session_per_track_with_times():
    o = _offering()
    assert o is not None
    labels = {s.label for s in o.schedule.sessions}
    assert labels == {"Classical ballet", "Contemporary dance"}
    by_label = {s.label: s for s in o.schedule.sessions}
    assert by_label["Classical ballet"].notes is not None
    assert "Marcello Algeri" in by_label["Classical ballet"].notes
    assert "14:00–15:30" in by_label["Classical ballet"].notes
    # Dotted source times normalize to colon form.
    assert by_label["Contemporary dance"].notes is not None
    assert "16:00–17:30" in by_label["Contemporary dance"].notes


def test_teachers_with_track_roles():
    o = _offering()
    assert o is not None
    by_name = {t.name: t for t in o.teachers}
    assert by_name["Marcello Algeri"].role == "Classical ballet"
    assert by_name["Jordan James Bridge"].role == "Contemporary dance"


def test_prices_per_track_and_combined():
    o = _offering()
    assert o is not None
    amounts = {(p.amount, p.label) for p in o.prices}
    assert (10000.0, "Per hour (single workshop)") in amounts
    assert (40000.0, "5-day pass (single workshop)") in amounts
    assert (80000.0, "5-day combined pass (classical + contemporary)") in amounts
    # The two tracks share figures — they must be deduped, not doubled.
    assert sum(1 for p in o.prices if p.amount == 10000.0) == 1
    assert all(p.currency == "HUF" for p in o.prices)
    assert all("tuition" in p.includes for p in o.prices)


def test_open_enrollment_no_audition_requirement():
    o = _offering()
    assert o is not None
    assert o.application.requirements == [NoneReq()]
    assert o.application.notes is not None
    assert "application@gyoribalett.hu" in o.application.notes
