"""Unit tests for the Young Stars Ballet scraper (Wix, two pages).

These pin the regex parsing of the Berlin summer-intensive pages: the two dated
editions, the age band, the EUR price (with the Wix zero-width space stripped),
the curriculum genres, the named guest teacher (without the ALL-CAPS heading
that follows it), and the application-form requirements. Inline strings, no
network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq
from intensive_dance.scrapers import young_stars_ballet as ysb


def test_sessions_two_editions():
    text = "YSB 1 | 16 JULY - 26 JULY 2026 YSB2 | 29 JULY - 8 AUGUST 2026"
    assert [(s.label, s.start, s.end) for s in ysb._sessions(text)] == [
        ("YSB 1", date(2026, 7, 16), date(2026, 7, 26)),
        ("YSB 2", date(2026, 7, 29), date(2026, 8, 8)),
    ]


def test_age_range():
    assert ysb._age_range("AGES: 13 - 21") == {"min": 13, "max": 21}


def test_price_with_zero_width_space_stripped():
    # The _text() pass removes Wix's zero-width spaces; here we feed cleaned text.
    prices = ysb._prices(
        "PRICE: €740 10 DAYS OF TRAINING ... 15% discount on your total course fee"
    )
    assert (prices[0].amount, prices[0].currency, prices[0].includes) == (740.0, "EUR", ["tuition"])
    assert "discount" in (prices[0].notes or "")


def test_genres():
    text = "BALLET CLASS TECHNIQUE SOLO REPERTOIRE MODERN MOVEMENT CORPS DE BALLET REHEARSAL POINTE TECHNIQUE"
    assert ysb._genres(text) == ["classical", "repertoire", "contemporary", "pointe"]


def test_teacher_name_without_trailing_heading():
    # "… by Melike Demirtas WHEN:" must not swallow the ALL-CAPS heading.
    teachers = ysb._teachers("Balletmasterclass by Melike Demirtas WHEN: YSB 1 | 16 JULY")
    assert [(t.name, t.role) for t in teachers] == [("Melike Demirtas", "Masterclass")]


def test_teacher_absent():
    assert ysb._teachers("a summer intensive with daily classes") == []


def test_requirements_headshot_poses_cv_no_video():
    apply_text = (
        "Photo upload: Headshot * 2-3 dance poses * (For example: arabesque) "
        "CV or letter * (Upload your CV detailing your previous dance experience)"
    )
    reqs = ysb._requirements(apply_text)
    assert {r.type for r in reqs} == {"headshot", "photos", "cv"}
    photos = next(r for r in reqs if isinstance(r, PhotosReq))
    assert photos.specificity == "freeform"


def test_zero_width_regex_strips():
    raw = "PRICE:" + "\u200b" + " " + "\u200c" + "\u20ac740"  # zwsp + non-joiner, as Wix emits
    assert ysb._ZERO_WIDTH.sub("", raw) == "PRICE: \u20ac740"
