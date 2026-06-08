"""Tests for the Canada's National Ballet School scraper.

All tests are offline — no network. The HTML fixtures mirror the live
``div.article-content`` structure captured 2026-06-08 (the two summer event
pages: Young Dancers Program Summer Immersion and the Adult Ballet Summer
Intensive).
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers.canadas_national_ballet_school import (
    EVENTS,
    _age_range,
    _build_offerings,
    _genres,
    _levels,
    _parse_range,
    _requirements,
    _track_prose,
)

# Index the EVENTS registry by path for the fixtures below.
_YDP = next(e for e in EVENTS if "young-dancers" in e.path)
_ADULT = next(e for e in EVENTS if "adult" in e.path)


# A faithful slice of the Young Dancers Program Summer Immersion event page:
# the headline date in <meta name="description">, og:title, and the two streams
# inside div.article-content with their register / apply anchors.
YDP_HTML = """
<html><head>
  <title>Young Dancers Program - Summer Immersion - Events | NBS</title>
  <meta name="description" content="August 4-14, 2026">
  <meta property="og:title" content="Young Dancers Program - Summer Immersion">
</head><body>
  <main>
    <div class="article-content col-12">
      <h2>Young Dancers Program - Summer Immersion</h2>
      <p><span>August 4-14, 2026</span></p>
      <p>Choose your perfect summer dance experience from two streams!</p>
      <p><strong><u>Open Dance</u></strong></p>
      <p>With two age groups to choose from, dancers ages 7-18 can enjoy a daily
         ballet class and explore different dance forms such as hip hop,
         contemporary, and jazz. Learn from NBS' expert dance educators.</p>
      <p>No application or audition is required.</p>
      <p><strong>Register for
         <a href="https://app.amilia.com/store/en/nbs-enb/api/Program/Detail?programId=ABC&subCategoryIds=1">Summer Immersion: Open Dance</a>
         stream.</strong></p>
      <p><u><strong>Intensive Ballet</strong></u></p>
      <p>For experienced dancers looking for an intensive summer dance experience.
         This stream focuses on stage-performance to help dancers prepare for
         their 2026/27 season through daily repertoire and choreography classes,
         specialized workshops, and a concluding presentation.</p>
      <p>Please Note: Admission to Summer Immersion: Intensive Ballet is by
         application only. A placement class will be held on the first day.
         Dancers should have a minimum of 3-4 years of dance training.</p>
      <p><strong>Submit an application for
         <a href="https://nbsdm.ca1.qualtrics.com/jfe/form/SV_x">Summer Immersion: Intensive Ballet</a>
         stream.</strong></p>
    </div>
  </main>
</body></html>
"""

# The Adult Ballet Summer Intensive page: two dated level-tracks, the second of
# which ("Beginner") is marked Full. Date headings are themselves the per-track
# date ranges, so they override the headline (Aug 4-15) range.
ADULT_HTML = """
<html><head>
  <meta name="description" content="August 4-15, 2026">
  <meta property="og:title" content="Adult Ballet Summer Intensive">
</head><body>
  <div class="article-content">
    <h2>Adult Ballet Summer Intensive</h2>
    <p>Dance with us in August! Classes include: Ballet, Conditioning,
       Ballet composition/repertoire.</p>
    <p><strong>August 4-8, 2026</strong></p>
    <p><strong>Elementary Level</strong></p>
    <p><strong>Intermediate Level</strong></p>
    <p><strong>August 11-15, 2026</strong></p>
    <p><b>Beginner Level - Full</b></p>
  </div>
</body></html>
"""


# ---------------------------------------------------------------------------
# _parse_range
# ---------------------------------------------------------------------------


def test_parse_range_single_month() -> None:
    assert _parse_range("August 4-14, 2026") == (date(2026, 8, 4), date(2026, 8, 14))


def test_parse_range_cross_month() -> None:
    assert _parse_range("June 28 – July 5, 2026") == (date(2026, 6, 28), date(2026, 7, 5))


def test_parse_range_no_match() -> None:
    assert _parse_range("no dates here") == (None, None)


# ---------------------------------------------------------------------------
# _genres / _levels / _age_range / _requirements (helper units)
# ---------------------------------------------------------------------------


def test_genres_open_dance_multi_style() -> None:
    prose = "daily ballet class and explore hip hop, contemporary, and jazz"
    assert _genres(prose) == ["classical", "contemporary"]


def test_genres_intensive_ballet_repertoire() -> None:
    prose = "daily repertoire and choreography classes and a concluding presentation"
    assert _genres(prose) == ["classical", "repertoire"]


def test_genres_default_classical() -> None:
    assert _genres("conditioning and composition") == ["classical"]


def test_levels_experienced_is_preprofessional() -> None:
    assert _levels("For experienced dancers looking for an intensive") == ["pre-professional"]


def test_levels_named_words() -> None:
    assert _levels("Elementary Level and Intermediate Level") == ["intermediate"]
    assert _levels("Beginner Level - Full") == ["beginner"]


def test_age_range_open_dance() -> None:
    assert _age_range("dancers ages 7-18 can enjoy") == {"min": 7, "max": 18}


def test_age_range_absent() -> None:
    assert _age_range("no ages stated here") is None


def test_requirements_none_when_open() -> None:
    reqs = _requirements("No application or audition is required.")
    assert [r.type for r in reqs] == ["none"]


def test_requirements_video_when_application() -> None:
    reqs = _requirements("Admission is by application only. Submit an application for the stream.")
    assert len(reqs) == 1
    assert reqs[0].type == "video"
    assert reqs[0].specificity == "unspecific"


def test_requirements_empty_when_unstated() -> None:
    assert _requirements("Choose from three levels.") == []


# ---------------------------------------------------------------------------
# _track_prose isolation (genres must not leak across streams)
# ---------------------------------------------------------------------------


def test_track_prose_isolates_streams() -> None:
    article = (
        "Open Dance ages 7-18 hip hop contemporary jazz Intensive Ballet repertoire choreography"
    )
    open_prose = _track_prose(article, "Open Dance")
    intensive_prose = _track_prose(article, "Intensive Ballet")
    assert "hip hop" in open_prose and "repertoire" not in open_prose
    assert "repertoire" in intensive_prose and "hip hop" not in intensive_prose


# ---------------------------------------------------------------------------
# _build_offerings — YDP Summer Immersion (two streams)
# ---------------------------------------------------------------------------


def test_build_ydp_two_streams() -> None:
    url = "https://www.nbs-enb.ca/events/young-dancers-program-summer-immersion"
    offerings = _build_offerings(YDP_HTML, url, _YDP)
    assert len(offerings) == 2
    by_id = {o.id: o for o in offerings}

    open_dance = by_id["canadas-national-ballet-school/open-dance-2026"]
    assert open_dance.schedule.start == date(2026, 8, 4)
    assert open_dance.schedule.end == date(2026, 8, 14)
    assert open_dance.age_range == {"min": 7, "max": 18}
    assert open_dance.genres == ["classical", "contemporary"]
    assert [r.type for r in open_dance.application.requirements] == ["none"]
    assert open_dance.application.url is not None
    assert "amilia.com" in open_dance.application.url
    assert open_dance.location is not None
    assert open_dance.location.country == "CA"

    intensive = by_id["canadas-national-ballet-school/intensive-ballet-2026"]
    assert intensive.schedule.start == date(2026, 8, 4)
    assert intensive.schedule.end == date(2026, 8, 14)
    assert intensive.genres == ["classical", "repertoire"]
    assert intensive.level == ["pre-professional"]
    assert intensive.age_range is None
    assert [r.type for r in intensive.application.requirements] == ["video"]
    assert intensive.application.url is not None
    assert "qualtrics.com" in intensive.application.url


# ---------------------------------------------------------------------------
# _build_offerings — Adult Ballet Summer Intensive (two dated tracks)
# ---------------------------------------------------------------------------


def test_build_adult_two_tracks() -> None:
    url = "https://www.nbs-enb.ca/events/adult-ballet-summer-intensive"
    offerings = _build_offerings(ADULT_HTML, url, _ADULT)
    assert len(offerings) == 2
    by_id = {o.id: o for o in offerings}

    week1 = by_id["canadas-national-ballet-school/adult-week-1-2026"]
    # The track heading "August 4-8, 2026" overrides the headline (Aug 4-15) range.
    assert week1.schedule.start == date(2026, 8, 4)
    assert week1.schedule.end == date(2026, 8, 8)
    assert week1.level == ["intermediate"]
    assert week1.genres == ["classical"]
    # No audition policy stated for adults → requirements left empty (not [NoneReq]).
    assert week1.application.requirements == []

    week2 = by_id["canadas-national-ballet-school/adult-week-2-2026"]
    assert week2.schedule.start == date(2026, 8, 11)
    assert week2.schedule.end == date(2026, 8, 15)
    assert week2.level == ["beginner"]


# ---------------------------------------------------------------------------
# Edge: missing article-content → tracks fall back to the headline range only
# ---------------------------------------------------------------------------


def test_build_offerings_missing_article() -> None:
    html = (
        '<html><head><meta name="description" content="August 4-14, 2026">'
        "</head><body></body></html>"
    )
    offerings = _build_offerings(html, "https://example.test", _YDP)
    # Both streams still emit (discovery is registry-driven), dated from headline,
    # with no genres leaking — genres fall back to the classical default.
    assert len(offerings) == 2
    for o in offerings:
        assert o.schedule.start == date(2026, 8, 4)
        assert o.schedule.end == date(2026, 8, 14)
        assert o.genres == ["classical"]
        assert o.application.url is None
