"""Unit tests for the Académie de Danse Princesse Grace scraper (Drupal page).

These pin the regex parsing of the one short-courses page: the four weekly
sessions emitted as independent Offerings (year only on the closing date),
the age band, the two EUR price tiers and their `includes`, the curriculum
genres, and — the richest part — the audition requirement set with its named
photo poses. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq, VideoReq
from intensive_dance.scrapers import academie_princesse_grace as pg

_DATES = (
    "From Monday July, 6th to Saturday July, 11th 2026 "
    "From Monday July, 13th to Saturday July, 18th 2026 "
    "From Monday July, 20th to Saturday July, 25th 2026 "
    "From Monday July, 27th to Saturday August, 1st 2026"
)


def test_week_dates_four_weeks_with_shared_year():
    pairs = pg._week_dates(_DATES)
    assert pairs == [
        (date(2026, 7, 6), date(2026, 7, 11)),
        (date(2026, 7, 13), date(2026, 7, 18)),
        (date(2026, 7, 20), date(2026, 7, 25)),
        (date(2026, 7, 27), date(2026, 8, 1)),
    ]


def test_week_dates_absent():
    assert pg._week_dates("no dated weeks here") == []


def test_build_offerings_four_separate_offerings():
    """Each weekly session becomes its own Offering with distinct start/end and id."""
    # Minimal HTML that exercises the full parse path
    html = (
        "<body>"
        "<p>For students between 11 and 19 years old. "
        "Possible audition for season 2026-2027 (only for students aged 13 to 17, "
        "born between 2013 and 2009).</p>"
        "<p>The courses are accessible after selection. "
        "Access is possible after audition.</p>"
        "<h4>" + _DATES + "</h4>"
        "<p>Curriculum: Classical, Contemporary, Pointe, Men's class, Pilates.</p>"
        "<p>Prices: 1200€/week (tuition + accommodation), "
        "700€/week (accommodation not included; optional meals available)</p>"
        "<p>please prepare: your CV/Resume, 1 ID photo and 2 dance outfit "
        "photos (poses arabesque and développé seconde), "
        "a video link of a classical extract with exercises, "
        "a video link with contemporary extract. "
        "Total video duration must not exceed: 15 minutes</p>"
        "</body>"
    )
    offerings = pg._build_offerings(html)
    assert len(offerings) == 4

    ids = [o.id for o in offerings]
    assert ids == [
        "academie-princesse-grace/summer-course-2026-w1",
        "academie-princesse-grace/summer-course-2026-w2",
        "academie-princesse-grace/summer-course-2026-w3",
        "academie-princesse-grace/summer-course-2026-w4",
    ]

    starts = [o.schedule.start for o in offerings]
    ends = [o.schedule.end for o in offerings]
    assert starts == [date(2026, 7, 6), date(2026, 7, 13), date(2026, 7, 20), date(2026, 7, 27)]
    assert ends == [date(2026, 7, 11), date(2026, 7, 18), date(2026, 7, 25), date(2026, 8, 1)]

    # Each Offering is self-contained — no nested sessions list
    for o in offerings:
        assert o.schedule.sessions == []

    # Titles
    titles = [o.title for o in offerings]
    assert titles == [
        "Summer Course 2026 — Week 1",
        "Summer Course 2026 — Week 2",
        "Summer Course 2026 — Week 3",
        "Summer Course 2026 — Week 4",
    ]


def test_build_offerings_empty_when_no_dates():
    assert pg._build_offerings("<body>No schedule announced yet.</body>") == []


def test_age_range():
    assert pg._age_range("For students between 11 and 19 years old.") == {"min": 11, "max": 19}


def test_level_pre_professional_when_selection_and_audition_required():
    text = "The courses are accessible after selection. Access is possible after audition."
    assert pg._level(text) == ["pre-professional"]


def test_prices_two_tiers_with_includes():
    text = "Prices: 1200€/week (tuition + accommodation), 700€/week (accommodation not included; optional meals available)"
    prices = pg._prices(text)
    assert [(p.amount, p.currency, p.includes, p.label, p.notes) for p in prices] == [
        (1200.0, "EUR", ["tuition", "accommodation"], "Per week (tuition + accommodation)", None),
        (
            700.0,
            "EUR",
            ["tuition"],
            "Per week (accommodation not included)",
            "Optional meals available.",
        ),
    ]


def test_genres():
    assert pg._genres("Curriculum: Classical, Contemporary, Pointe, Men's class, Pilates") == [
        "classical",
        "contemporary",
        "pointe",
    ]


def test_requirements_full_audition_set_with_named_poses():
    text = (
        "please prepare the documentation: - your CV/Resume - 1 ID photo and 2 dance outfit "
        "photos (poses arabesque and développé seconde) - a video link of a classical extract "
        "with following exercises - a video link with contemporary extract. "
        "Total video duration must not exceed: 15 minutes"
    )
    reqs = pg._requirements(text)
    assert {r.type for r in reqs} == {"cv", "headshot", "photos", "video"}

    photos = next(r for r in reqs if isinstance(r, PhotosReq))
    assert photos.specificity == "defined-poses"
    assert photos.poses == ["arabesque", "développé seconde"]

    video = next(r for r in reqs if isinstance(r, VideoReq))
    assert video.specificity == "specific"
    assert "contemporary" in (video.description or "")
    assert "15 minutes" in (video.description or "")


def test_requirements_video_only_classical():
    reqs = pg._requirements("a video link of a classical extract with exercises")
    video = next(r for r in reqs if isinstance(r, VideoReq))
    assert "classical" in (video.description or "")
    assert "contemporary" not in (video.description or "")
