"""Unit tests for the Finnish National Ballet summer-intensive scraper.

The source is one WordPress page (Gutenberg blocks) served whole over the REST
API; `_build_offerings` takes that page record and emits two Offerings (the youth
intensive + the adult "Ballet in Bloom" track). These pin the judgement calls a
hash check can't catch: the two date spans ("from 20 to 25 July 2026" vs
"20–24 July 2026"), the 12-22 age band, EUR full/early-bird prices and their
meal inclusion, the per-offering requirement mix, the named faculty roles, and
the application-window → status derivation. Inline page dict, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import CVReq, HeadshotReq, PhotosReq, VideoReq
from intensive_dance.scrapers import finnish_national_ballet as fnb

# Trimmed but structurally faithful copy of the live page body: nav buttons (the
# "summer intensive" label collides with the real section heading), the youth
# body with dates + ages + curriculum, the Ballet in Bloom prose + schedule, two
# faculty <h3>/<p> blocks, the application window, and the tuition fee block.
_RENDERED = """
<div class="wp-block-button"><a href="#summer">summer intensive</a></div>
<div class="wp-block-button"><a href="#tuition">tuition</a></div>

<h2 id="intro">welcome to the  International Summer Intensive</h2>
<p>We are excited to welcome you again from 20 to 25 July 2026.</p>

<h2 id="summer">summer intensive</h2>
<p>The 6th edition of the International Summer Intensive will take place from
20 to 25 July 2026.</p>
<p>We thoroughly designed the program around participants aged 12&#8211;22.</p>
<p>Five daily lessons comprising classical ballet, pointe technique, repertoire,
character classes, as well as body conditioning.</p>
<p>Refine your classical technique under Giovanni di Palma, former Leipzig Ballet
principal and renowned coach, bringing unmatched expertise in neoclassical and
contemporary repertoire to elevate precision and artistry.</p>

<h3>New in 2026: Ballet in Bloom</h3>
<p>Participants will enjoy ballet classes, repertoire training, character dance,
and acting coaching.</p>
<h2>More info about Ballet in Bloom</h2>
<p>Ballet in Bloom includes 3 evening sessions daily, 20&#8211;24 July 2026,
from 17:00 to 21:00.</p>
<p>A minimum of five years of prior ballet training is recommended.</p>

<h2 id="faculty">faculty</h2>
<h3>Giovanni Di Palma</h3>
<p>Italy<br>Former principal dancer &#8211; Leipzig Ballet<br>Classical technique, Repertoire<br><a href="https://oopperabaletti.fi/cv.pdf">Read more (PDF)</a></p>
<h3>Juliette Rahon</h3>
<p>France<br>Rehearsal director &#8211; Ballet du Grand Th&#233;&#226;tre de Gen&#232;ve<br>Contemporary, Choreographer&#8217;s workshop<br><a href="https://oopperabaletti.fi/cv3.pdf">Read more (PDF)</a></p>
<h3>Jutta Mustakallio Ruusunen</h3>
<p>Finland<br>Character Dance Teacher<br>Character dance<br><a href="https://oopperabaletti.fi/cv2.pdf">Read more (PDF)</a></p>

<h2 id="application">how to apply</h2>
<p>Application dates are 15 December 2025 &#8211; 30 April 2026.</p>
<p><a href="https://www.lyyti.fi/reg/International_Summer_Intensive_2026_3322">apply online</a></p>

<h2 id="tuition">tuition</h2>
<p>Summer Intensive: &#8364;900 (VAT incl.)</p>
<p>Early bird campaign: &#8364;800 (VAT incl.), registration latest by 28.02.2026.</p>
<p>Sibling reduction: 25% off the normal price.</p>
<p>Ballet in Bloom: &#8364;450 (VAT incl.)</p>
<p>Early bird campaign: &#8364;375 (VAT incl.), registration latest by 28.02.2026.</p>
<p>The Summer Intensive tuition fee includes all classes and a warm lunch.</p>
<p>The Ballet in Bloom tuition fee includes all classes.</p>
"""

_PAGE = {
    "link": "https://oopperabaletti.fi/en/international-summer-intensive/",
    "content": {"rendered": _RENDERED},
}


def _offerings(today: date = date(2026, 1, 1)):
    return fnb._build_offerings(_PAGE, today)


def test_emits_both_offerings() -> None:
    ids = {o.id for o in _offerings()}
    assert ids == {
        "finnish-national-ballet/international-summer-intensive-2026",
        "finnish-national-ballet/ballet-in-bloom-2026",
    }


def test_summer_intensive_dates_ages_genres() -> None:
    main = _offerings()[0]
    assert main.schedule.start == date(2026, 7, 20)
    assert main.schedule.end == date(2026, 7, 25)
    assert main.schedule.season == "2026"
    assert main.age_range == {"min": 12, "max": 22}
    # Genres come from the curriculum sentence + teacher roles, NOT teacher bios.
    # Di Palma's bio mentions "neoclassical and contemporary repertoire" but that
    # is his credential, not a class — neoclassical must not be derived from it.
    # Contemporary IS correct: Juliette Rahon's role is "Contemporary, …".
    assert main.genres == [
        "classical",
        "pointe",
        "repertoire",
        "character",
        "contemporary",
    ]


def test_neoclassical_not_derived_from_teacher_bio() -> None:
    # The summer intensive body contains Di Palma's bio phrase
    # "neoclassical and contemporary repertoire" — this must not trigger
    # the neoclassical genre; only the "Five daily lessons…" curriculum line
    # and teacher role subjects are authoritative for genre matching.
    main = _offerings()[0]
    assert "neoclassical" not in main.genres


def test_ballet_in_bloom_dates_level_genres() -> None:
    bloom = _offerings()[1]
    assert bloom.schedule.start == date(2026, 7, 20)
    assert bloom.schedule.end == date(2026, 7, 24)
    assert bloom.age_range is None
    assert bloom.level == ["open"]
    assert bloom.genres == ["classical", "repertoire", "character"]


def test_prices_and_meal_inclusion() -> None:
    main, bloom = _offerings()
    assert [(p.amount, p.label, tuple(p.includes)) for p in main.prices] == [
        (900.0, "Tuition", ("tuition", "meals")),
        (800.0, "Early bird", ("tuition", "meals")),
    ]
    # Bloom fee covers classes only — no lunch.
    assert [(p.amount, tuple(p.includes)) for p in bloom.prices] == [
        (450.0, ("tuition",)),
        (375.0, ("tuition",)),
    ]
    assert all(p.currency == "EUR" for p in main.prices + bloom.prices)


def test_requirements_differ_per_offering() -> None:
    main, bloom = _offerings()
    main_types = [type(r) for r in main.application.requirements]
    assert main_types == [PhotosReq, VideoReq, CVReq]
    photos = main.application.requirements[0]
    assert isinstance(photos, PhotosReq)
    assert photos.specificity == "defined-poses"
    assert photos.poses == ["headshot", "1st arabesque"]
    # Ballet in Bloom: explicitly only a headshot.
    assert [type(r) for r in bloom.application.requirements] == [HeadshotReq]


def test_application_window_and_status() -> None:
    # Before the window opens.
    upcoming = fnb._build_offerings(_PAGE, date(2025, 1, 1))[0]
    assert upcoming.application.opens_at == date(2025, 12, 15)
    assert upcoming.application.deadline == date(2026, 4, 30)
    assert upcoming.application.status == "upcoming"
    # Within the window.
    assert _offerings(date(2026, 2, 1))[0].application.status == "open"
    # After the deadline but before the course ends → still emitted, status closed.
    after = fnb._build_offerings(_PAGE, date(2026, 6, 5))
    assert len(after) == 2
    assert after[0].application.status == "closed"


def test_course_dropped_once_it_has_ended() -> None:
    assert fnb._build_offerings(_PAGE, date(2026, 8, 1)) == []


def test_faculty_roles_from_teaching_subject() -> None:
    main = _offerings()[0]
    roles = {t.name: t.role for t in main.teachers}
    assert roles == {
        "Giovanni Di Palma": "Classical technique, Repertoire",
        "Juliette Rahon": "Contemporary, Choreographer’s workshop",
        "Jutta Mustakallio Ruusunen": "Character dance",
    }


def test_apply_url_is_lyyti() -> None:
    main = _offerings()[0]
    assert (
        main.application.url == "https://www.lyyti.fi/reg/International_Summer_Intensive_2026_3322"
    )
