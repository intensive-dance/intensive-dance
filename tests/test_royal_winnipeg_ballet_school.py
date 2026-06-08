"""Unit tests for the Royal Winnipeg Ballet School summer-programs scraper.

RWB is a clean WordPress REST scrape: programs are a `lesson` custom post type
whose dates/ages/fees/deadline live in ACF fields, while the disciplines for
genre matching live in `content.rendered` prose. These tests feed
`_build_offering` realistic `lesson` records (mirroring the live ACF + content
shapes) and pin each judgement call a hash check can't catch: the YYYYMMDD date
parse, the open-topped vs bounded age range, the CAD tuition parse, the
open/closed status from `event_available`, the freeform-photos requirement, and
the genre keyword match against curriculum prose only. No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq
from intensive_dance.scrapers import royal_winnipeg_ballet_school as rwb

# Dance Intensive (Recreational Division): bounded ages, a CAD tuition, a closed
# application with a deadline, and a curriculum naming pointe / modern-contemporary
# / repertoire-choreography / character (plus jazz, which has no Genre enum).
_DANCE_INTENSIVE = {
    "slug": "dance-intensive",
    "link": "https://www.rwb.org/school/programs-classes/dance-intensive/",
    "title": {"rendered": "Dance Intensive"},
    "content": {
        "rendered": (
            "<p>Classes are held daily, beginning with a ballet class, followed by a "
            "rotating schedule of various dance disciplines, including but not limited "
            "to pointe, conditioning, repertoire/choreography, modern/contemporary, jazz "
            "and character.</p>"
            "<p>Once the online application is received, a link will be sent to each "
            "applicant for the upload of two dance photos.</p>"
        )
    },
    "acf": {
        "event_available": False,
        "event_registration_deadline": "20260615",
        "event_age_range": "10-18",
        "event_location": "380 Graham Ave. ",
        "event_start_date": "20260804",
        "event_end_date": "20260815",
        "event_price": "$1150",
        "event_description": "A two-week summer training opportunity.",
    },
}

# Summer Session (Professional Division): open-topped age "10+", no price (price
# on acceptance), an open application with no deadline, and a curriculum naming
# ballet/pointe/character/modern/variations/repertoire/pas de deux but no photo
# step (it is itself the in-person audition phase) → empty requirements.
_SUMMER_SESSION = {
    "slug": "summer-session",
    "link": "https://www.rwb.org/school/programs-classes/summer-session/",
    "title": {"rendered": "Summer Session"},
    "content": {
        "rendered": (
            "<p>Classes will be offered in ballet and pointe technique, movement "
            "improvisation, historical dance, modern and character dance, conditioning, "
            "variations, repertoire and pas de deux and run from Monday to Saturday.</p>"
        )
    },
    "acf": {
        "event_available": True,
        "event_registration_deadline": None,
        "event_age_range": "10+",
        "event_location": "380 Graham Ave. ",
        "event_start_date": "20260706",
        "event_end_date": "20260725",
        "event_price": "",
        "event_description": "The second phase of the audition process.",
    },
}


# --- ACF dates ----------------------------------------------------------------


def test_acf_date_parses_yyyymmdd():
    assert rwb._acf_date("20260804") == date(2026, 8, 4)


def test_acf_date_none_when_empty_or_invalid():
    assert rwb._acf_date("") is None
    assert rwb._acf_date(None) is None
    assert rwb._acf_date("2026-08-04") is None
    assert rwb._acf_date("20261342") is None  # month 13 / day 42


# --- ages ---------------------------------------------------------------------


def test_age_range_bounded():
    assert rwb._age_range("10-18") == {"min": 10, "max": 18}


def test_age_range_open_topped():
    assert rwb._age_range("10+") == {"min": 10, "max": None}


def test_age_range_absent():
    assert rwb._age_range(None) is None
    assert rwb._age_range("all ages") is None


# --- genres -------------------------------------------------------------------


def test_genres_from_curriculum_prose():
    text = (
        "ballet and pointe technique, modern and character dance, variations, "
        "repertoire and pas de deux"
    )
    assert rwb._genres(text) == [
        "classical",
        "pointe",
        "character",
        "contemporary",
        "repertoire",
    ]


def test_genres_default_classical_when_only_ballet():
    assert rwb._genres("a ballet-focused program") == ["classical"]


# --- prices -------------------------------------------------------------------


def test_prices_cad_tuition():
    (price,) = rwb._prices("$1150")
    assert (price.amount, price.currency, price.includes) == (1150.0, "CAD", ["tuition"])


def test_prices_empty_when_no_amount():
    assert rwb._prices("") == []
    assert rwb._prices(None) == []


# --- application status -------------------------------------------------------


def test_status_open_closed_unknown():
    assert rwb._status(True) == "open"
    assert rwb._status(False) == "closed"
    assert rwb._status(None) is None


# --- requirements -------------------------------------------------------------


def test_requirements_freeform_photos_when_photo_step_stated():
    (req,) = rwb._requirements("upload of two dance photos after applying")
    assert isinstance(req, PhotosReq)
    assert req.specificity == "freeform"


def test_requirements_empty_when_silent():
    assert rwb._requirements("an in-person audition phase") == []


# --- location -----------------------------------------------------------------


def test_location_venue_city_country():
    loc = rwb._location("380 Graham Ave. ")
    assert (loc.venue, loc.city, loc.country) == ("380 Graham Ave.", "Winnipeg", "CA")


def test_location_no_venue():
    loc = rwb._location(None)
    assert (loc.venue, loc.city, loc.country) == (None, "Winnipeg", "CA")


# --- end-to-end ---------------------------------------------------------------


def test_dance_intensive_offering():
    o = rwb._build_offering(_DANCE_INTENSIVE, date(2026, 1, 1))
    assert o is not None
    assert o.id == "royal-winnipeg-ballet-school/dance-intensive-2026"
    assert o.title == "Dance Intensive"
    assert o.schedule.season == "2026"
    assert o.schedule.start == date(2026, 8, 4)
    assert o.schedule.end == date(2026, 8, 15)
    assert o.schedule.timezone == "America/Winnipeg"
    assert o.age_range == {"min": 10, "max": 18}
    assert o.genres == ["classical", "pointe", "character", "contemporary", "repertoire"]
    assert o.location is not None
    assert (o.location.venue, o.location.city, o.location.country) == (
        "380 Graham Ave.",
        "Winnipeg",
        "CA",
    )
    assert [(p.amount, p.currency, p.includes) for p in o.prices] == [(1150.0, "CAD", ["tuition"])]
    assert o.application.status == "closed"
    assert o.application.deadline == date(2026, 6, 15)
    assert o.application.requirements[0].type == "photos"


def test_summer_session_offering():
    o = rwb._build_offering(_SUMMER_SESSION, date(2026, 1, 1))
    assert o is not None
    assert o.id == "royal-winnipeg-ballet-school/summer-session-2026"
    assert o.schedule.start == date(2026, 7, 6)
    assert o.schedule.end == date(2026, 7, 25)
    assert o.age_range == {"min": 10, "max": None}
    assert o.genres == ["classical", "pointe", "character", "contemporary", "repertoire"]
    assert o.prices == []  # price on acceptance — event_price is empty
    assert o.application.status == "open"
    assert o.application.deadline is None
    assert o.application.requirements == []  # audition phase states no submitted material


def test_no_offering_when_start_date_absent():
    record = {
        "slug": "summer-session",
        "link": "https://www.rwb.org/x/",
        "title": {"rendered": "Summer Session"},
        "content": {"rendered": "<p>ballet</p>"},
        "acf": {"event_start_date": None, "event_end_date": None},
    }
    assert rwb._build_offering(record, date(2026, 1, 1)) is None
