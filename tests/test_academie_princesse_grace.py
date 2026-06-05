"""Unit tests for the Académie de Danse Princesse Grace scraper (Drupal page).

These pin the regex parsing of the one short-courses page: the four weekly
sessions (year only on the closing date), the age band, the two EUR price tiers
and their `includes`, the curriculum genres, and — the richest part — the
audition requirement set with its named photo poses. Inline strings, no network.
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


def test_sessions_four_weeks_with_shared_year():
    sessions = pg._sessions(_DATES)
    assert [(s.label, s.start, s.end) for s in sessions] == [
        ("Week 1", date(2026, 7, 6), date(2026, 7, 11)),
        ("Week 2", date(2026, 7, 13), date(2026, 7, 18)),
        ("Week 3", date(2026, 7, 20), date(2026, 7, 25)),
        ("Week 4", date(2026, 7, 27), date(2026, 8, 1)),
    ]


def test_sessions_absent():
    assert pg._sessions("no dated weeks here") == []


def test_age_range():
    assert pg._age_range("For students between 11 and 19 years old.") == {"min": 11, "max": 19}


def test_prices_two_tiers_with_includes():
    text = "Prices: 1200€/week (tuition + accommodation), 700€/week (accommodation not included; optional meals available)"
    prices = pg._prices(text)
    assert [(p.amount, p.currency, p.includes) for p in prices] == [
        (1200.0, "EUR", ["tuition", "accommodation"]),
        (700.0, "EUR", ["tuition"]),
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
