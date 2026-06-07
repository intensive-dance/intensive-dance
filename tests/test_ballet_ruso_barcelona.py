"""Unit tests for the Ballet Ruso Barcelona scraper (Tilda summer page).

These pin the parsing of the one Summer Program page: the year lifted from the
header, the pre-professional weekly `DD.MM - DD.MM` sessions, the open-ended age
band, the tuition tiers, the genre matching, and the dual live/online audition
mapping to a `VideoReq`. They also pin that the recreational Young Artist Camp
(age 3+) is deliberately skipped. Inline strings shaped like the live HTML text,
no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import ballet_ruso_barcelona as brb

# A trimmed copy of the page's visible text, in document order, keeping the
# markers the scraper slices on and the Spanish DD.MM week ranges.
_PAGE = (
    "ballet ruso barcelona Summer Intensive 2026 June 29 - July 24, 2026 "
    "Under the supervision of BRB Artistic Directors Boris Shepelev and Blanca Hartmann . "
    "Ballet Technique Pointe Pre-pointe (younger students) Partnering Female Variations "
    "Men's Technique & Variations Historical Dance Character Dance Contemporary Dance Jazz "
    "Pilates Physical Conditioning Stretching Class concert "
    "BRB's teaching philosophy for this age is to develop a versatile artist with a strong "
    "classical ballet technique . Thus, kids willd be exposed to a classical ballet tecnique "
    "lesson followed by jazz, musical theatre, singing, drama & modern dance . "
    "PRE-PROFESSIONAL program Age: from 10 years old (born in 2015 or before) "
    "Schedule: M-F, 09.30 - 16.00 Dates*: "
    "Week #1: 29.06 - 03.07 Week #2: 06.07 - 10.07 Week #3: 13.07 - 17.07 Week #4: 20.07 - 24.07 "
    "Tuition: 1 week: 537€ 2 weeks: 975€ 3 weeks: 1296€ 4 weeks: 1495€ "
    "YOUNG ARTIST camp Age: from 3 years old (born in 2022 or before) "
    "Schedule : M-F, 09.30 - 16.00 Dates*: "
    "Week #0: 22.06 - 26.06 Week #1: 29.06 - 03.07 Week #2: 06.07 - 10.07 "
    "Week #3: 13.07 - 17.07 Week #4: 20.07 - 24.07 "
    "Tuition for week 1,2,3 or 4*: 1 week: 356€ 2 weeks: 637€ 3 weeks: 844€ 4 weeks: 975€ "
    "5 weeks: 1100€ "
    "Terms and conditions Refunds No refunds will be made. "
    "Students applying for the pre-professional program must attend an audition or audition "
    "on-line. Live-audition cost: €30 On-line audition cost: €15 "
    "You will be informed of the results of the audition within 2 weeks."
)


def _build():
    return brb._build_offerings(f"<html><body>{_PAGE}</body></html>", date(2026, 1, 1))


def test_year_from_header():
    assert brb._year(_PAGE) == 2026


def test_emits_pre_professional_only_camp_skipped():
    # The Young Artist Camp (age 3+, recreational) is deliberately not emitted.
    offerings = _build()
    assert [o.title for o in offerings] == ["Summer Intensive 2026 — Pre-professional Program"]
    assert [o.id for o in offerings] == [
        "ballet-ruso-barcelona/summer-intensive-2026-pre-professional",
    ]
    assert all("young-artist-camp" not in o.id for o in offerings)


def test_pre_professional_sessions_four_weeks():
    pre = _build()[0]
    assert [(s.label, s.start, s.end) for s in pre.schedule.sessions] == [
        ("Week #1", date(2026, 6, 29), date(2026, 7, 3)),
        ("Week #2", date(2026, 7, 6), date(2026, 7, 10)),
        ("Week #3", date(2026, 7, 13), date(2026, 7, 17)),
        ("Week #4", date(2026, 7, 20), date(2026, 7, 24)),
    ]
    assert pre.schedule.start == date(2026, 6, 29)
    assert pre.schedule.end == date(2026, 7, 24)


def test_age_range_open_upper_bound():
    (pre,) = _build()
    assert pre.age_range == {"min": 10, "max": None}


def test_prices_tuition_tiers():
    (pre,) = _build()
    assert [(p.label, p.amount, p.includes) for p in pre.prices] == [
        ("1 week", 537.0, ["tuition"]),
        ("2 weeks", 975.0, ["tuition"]),
        ("3 weeks", 1296.0, ["tuition"]),
        ("4 weeks", 1495.0, ["tuition"]),
    ]


def test_genres_from_pre_professional_curriculum():
    (pre,) = _build()
    # The pre-professional slice's own curriculum names Pointe and Character.
    assert "pointe" in pre.genres
    assert "character" in pre.genres


def test_pre_professional_audition_video_unspecific():
    pre = _build()[0]
    reqs = pre.application.requirements
    assert len(reqs) == 1
    video = reqs[0]
    assert isinstance(video, VideoReq)
    assert video.specificity == "unspecific"
    assert "€30" in (video.description or "") and "€15" in (video.description or "")


def test_directors_named_with_lineage():
    pre = _build()[0]
    names = {t.name for t in pre.teachers}
    assert names == {"Boris Shepelev", "Blanca Hartmann"}
    boris = next(t for t in pre.teachers if t.name == "Boris Shepelev")
    assert any("Mariinsky" in a.organization for a in boris.affiliations)


def test_no_year_no_offerings():
    assert (
        brb._build_offerings("<html><body>nothing dated here</body></html>", date(2026, 1, 1)) == []
    )


def test_apply_url_is_audition_page():
    # The HOW TO APPLY section on the live page links to actividad/60 (the audition
    # form), not actividad/59 (a camp registration page).
    assert "actividad/60" in brb.APPLY_URL
    assert "Audition" in brb.APPLY_URL
