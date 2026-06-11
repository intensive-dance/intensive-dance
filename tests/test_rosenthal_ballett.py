"""Offline tests for the Rosenthal Ballett (Summer Intensive) scraper.

Inline HTML mirrors the Wix SSR body (with zero-width spaces). No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import rosenthal_ballett as rb

# Embeds zero-width spaces (​) like the real Wix markup, to prove they are stripped.
HTML = """
<html><head><script>var x = "ignore 999€";</script></head>
<body>
<h1>Summer Intensive 2026</h1>
<p>The Rosenthal Ballett Summer Intensive 2026 ... Led by an exceptional faculty of
internationally renowned ballet artists, including Caroline Llorca, Csaba Kvasz,
Stéphane Dalle, Kauan Soares, Sébastien Mari , and distinguished guest teachers,
this intensive ... daily schedule of small groups (approximately 5 hours), which includes:
Floor Barre Boris Kniaseff method (50min) Classical Ballet Technique (60min)
Variation Coaching (90min) Repertoire Focus with special emphasis on the works of
Jiří Kylián (90min) Set in the heart of Düsseldorf, ...</p>
<p>​📅 Dates: 21 July – 2 August 2026 📍 Location: Rosenthal-Ballett in Düsseldorf, Germany
💶 Fee: 890€ (two-week program) Admission by Video Audition Only Two small groups will be formed:
- Group A : Younger dance students (min. 13 to 15 years) or those at a certain level (pre professional)
- Group B : More experienced professional dance students and dancers (min 16 to 19 years)
🎥 Video Submission Deadline: April 30th, 2026 Submit via: YouTube ...
Video Audition Requirements ... Barre - Plié - Tendu (one exercise) - Adagio - Grand Battement
Center (Girls on pointe from Adagio to Petit Allegro) - Adagio - Grand Allegro (Boys: include tours)</p>
</body></html>
"""


def test_core_fields():
    o = rb._build_offering(HTML)
    assert o.id == "rosenthal-ballett/summer-intensive-2026"
    assert o.title == "Summer Intensive 2026"
    assert o.schedule.start == date(2026, 7, 21)
    assert o.schedule.end == date(2026, 8, 2)
    assert o.location is not None
    assert o.location.city == "Düsseldorf"


def test_two_age_only_sessions_and_band():
    o = rb._build_offering(HTML)
    labels = [s.label for s in o.schedule.sessions]
    assert labels == ["Group A", "Group B"]
    assert o.schedule.sessions[0].age_range == {"min": 13, "max": 15}
    assert o.schedule.sessions[1].age_range == {"min": 16, "max": 19}
    assert o.age_range == {"min": 13, "max": 19}
    # the full blurb is kept, not truncated at "min."
    assert "pre professional" in (o.schedule.sessions[0].notes or "")


def test_genres_price_faculty():
    o = rb._build_offering(HTML)
    assert o.genres == ["classical", "repertoire", "contemporary"]
    assert len(o.prices) == 1
    assert o.prices[0].amount == 890.0  # the 999 inside <script> is ignored
    assert o.prices[0].currency == "EUR"
    names = [t.name for t in o.teachers]
    assert names == [
        "Caroline Llorca",
        "Csaba Kvasz",
        "Stéphane Dalle",
        "Kauan Soares",
        "Sébastien Mari",
    ]


def test_video_audition_and_deadline():
    o = rb._build_offering(HTML)
    assert o.application.deadline == date(2026, 4, 30)
    assert len(o.application.requirements) == 1
    req = o.application.requirements[0]
    assert isinstance(req, VideoReq)
    assert req.specificity == "specific"
    assert "Grand Battement" in (req.description or "")
