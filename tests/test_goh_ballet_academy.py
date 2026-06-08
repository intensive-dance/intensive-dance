"""Unit tests for the Goh Ballet Academy (Vancouver) summer-intensives scraper.

Goh is a clean WordPress REST scrape: the Vancouver summer offerings are one
`programs` record whose `acf.contents` repeater holds one `class_information`
block per summer offering. The dated edition + age band are encoded in the block
`name`; the curriculum / levels / dated sub-sessions live in nested ACF layouts.
These feed `_build_offerings` a record mirroring the live ACF shape and pin each
judgement call: the in-scope filter (day-specific date + age floor 7+ keeps the
intensives, drops the children's camps and the bare cross-link blocks), the
open-topped "7-18+" age parse, the two-session split, the genre match against the
Curriculum list only, the audition requirement, and that no price is invented. No
network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import goh_ballet_academy as goh


def _accordion(curriculum: list[str], levels: list[str], list_with_title: bool = False) -> dict:
    cur_layout = (
        {
            "acf_fc_layout": "list_with_title",
            "list_with_title": {"title": "", "list": [{"text": t} for t in curriculum]},
        }
        if list_with_title
        else {"acf_fc_layout": "list", "list": [{"text": t} for t in curriculum]}
    )
    return {
        "acf_fc_layout": "accordion_set",
        "title": "",
        "accordion": [
            {
                "title": "Levels",
                "acc_inside_contents": [
                    {"acf_fc_layout": "list", "list": [{"text": t} for t in levels]}
                ],
            },
            {"title": "Curriculum", "acc_inside_contents": [cur_layout]},
            {
                "title": "Guest Instructors",
                "acc_inside_contents": [{"acf_fc_layout": "title_set", "title": "TBA"}],
            },
        ],
    }


# Block 2 — Ballet & Beyond: open-topped ages, two dated sub-sessions in a
# list_set, a Curriculum list naming ballet/pointe/repertoire/pas de deux/
# contemporary, and an Eventbrite audition link.
_BALLET_AND_BEYOND: dict = {
    "acf_fc_layout": "class_information",
    "name": (
        "Ballet &amp; Beyond – July International Summer Intensive "
        '<p style="margin-top:-0.5em"><span style="font-size:0.75em">'
        "Ages 7-18+ | July 6–31, 2026</span></p>"
    ),
    "main_contents": [
        {"acf_fc_layout": "text_area_set", "text_area": "<p>A summer shaped by artistry.</p>"},
        {
            "acf_fc_layout": "list_set",
            "list": [
                {
                    "text": (
                        "<strong>Session One – Competition Preparation and Performance "
                        "Essentials: July 6–17, 2026</strong> <p>Train through the eyes "
                        "of an adjudicator.</p>"
                    )
                },
                {
                    "text": (
                        "<strong>Session Two – Choreography, Repertoire, and Beyond: "
                        "July 20–31, 2026</strong> <p>Expression takes center stage.</p>"
                    )
                },
            ],
        },
        _accordion(
            curriculum=[
                "Classical Ballet",
                "Pointe Work",
                "Repertoire &amp; Variations",
                "Partnering/Pas de Deux",
                "Contemporary Dance",
                "Performance, Competition &amp; Audition Preparation",
            ],
            levels=[
                "<strong>En Marché;</strong> early steps and exploration of movement",
                "<strong>En Lien;</strong> emphasis on transitioning movements and flow",
                "<strong>En Vitesse;</strong> increasing agility and dynamics",
                "<strong>En Volée;</strong> emphasis on artistry for advanced dancers",
            ],
        ),
        {
            "acf_fc_layout": "link_set",
            "link": {
                "title": "Audition Information",
                "url": "https://www.eventbrite.ca/e/vancouver-in-person-group-audition-1081293109799",
                "target": "",
            },
        },
    ],
}

# Block 3 — Passion & Precision: single dated span (no sub-session list), a
# Curriculum stored as list_with_title naming ballet/pointe/repertoire/pas de
# deux/contemporary (plus flamenco/musical theatre, which have no Genre enum).
_PASSION_AND_PRECISION: dict = {
    "acf_fc_layout": "class_information",
    "name": (
        "Passion &amp; Precision - August Summer Program "
        '<p><span style="font-size:0.75em">Ages 7-18+ | August 10–20, 2026</span></p>'
    ),
    "main_contents": [
        {"acf_fc_layout": "text_area_set", "text_area": "<p>Ten days of focused training.</p>"},
        _accordion(
            curriculum=[
                "Classical Ballet",
                "Pointe Technique Development",
                "Repertoire &amp; Variations",
                "Pas de Deux",
                "Contemporary Technique",
                "Flamenco",
                "Musical Theatre",
            ],
            levels=[
                "<strong>Aspen;</strong> wonder and discovery",
                "<strong>Cedar;</strong> develop skills and self identity",
                "<strong>Maple;</strong> develop artistry and unique qualities",
                "<strong>Spruce;</strong> professional practice and maturity",
            ],
            list_with_title=True,
        ),
        {
            "acf_fc_layout": "link_set",
            "link": {
                "title": "Audition Information",
                "url": "https://www.eventbrite.ca/e/vancouver-in-person-group-audition-1081293109799",
                "target": "",
            },
        },
    ],
}

# Out of scope: a children's camp (ages 4-7, month-only "July - August" span, no
# day numbers) and a bare cross-link block (no age, no date) — both must drop.
_CHILDRENS_CAMP: dict = {
    "acf_fc_layout": "class_information",
    "name": (
        "Children’s Summer Dance Camps "
        '<p><span style="font-size:0.75em">Ages 4-7 | July - August, 2026</span></p>'
    ),
    "main_contents": [
        {"acf_fc_layout": "text_area_set", "text_area": "<p>Budding dancers aged 4 to 7.</p>"}
    ],
}
_TORONTO_LINK: dict = {
    "acf_fc_layout": "class_information",
    "name": "Summer Programs Toronto",
    "main_contents": [
        {"acf_fc_layout": "link_set", "link": {"title": "View", "url": "https://x/", "target": ""}}
    ],
}

_RECORD = {
    "link": "https://www.gohballet.com/program/summer-programs/",
    "acf": {
        "contents": [
            _CHILDRENS_CAMP,
            _BALLET_AND_BEYOND,
            _PASSION_AND_PRECISION,
            _TORONTO_LINK,
        ]
    },
}


# --- name parsing -------------------------------------------------------------


def test_parse_name_title_ages_dates():
    title, ages, start, end, _ = goh._parse_name(_BALLET_AND_BEYOND["name"])
    assert title == "Ballet & Beyond – July International Summer Intensive"
    assert ages == {"min": 7, "max": None}  # the "+" opens the band
    assert start == date(2026, 7, 6)
    assert end == date(2026, 7, 31)


def test_parse_name_month_only_span_is_not_dated():
    # "July - August, 2026" has no day numbers → no day-specific range → not in scope.
    _, ages, start, end, _ = goh._parse_name(_CHILDRENS_CAMP["name"])
    assert start is None and end is None
    assert ages == {"min": 4, "max": 7}


def test_parse_name_bare_crosslink_has_no_age_or_date():
    title, ages, start, _, _ = goh._parse_name(_TORONTO_LINK["name"])
    assert title == "Summer Programs Toronto"
    assert ages is None and start is None


# --- slug ---------------------------------------------------------------------


def test_slug_drops_generic_tail():
    assert (
        goh._slug("Ballet & Beyond – July International Summer Intensive") == "ballet-beyond-july"
    )
    assert goh._slug("Passion & Precision - August Summer Program") == "passion-precision-august"


# --- genres (Curriculum list only) --------------------------------------------


def test_genres_from_curriculum():
    cur = goh._curriculum_text(_BALLET_AND_BEYOND)
    assert goh._genres(cur) == ["classical", "pointe", "contemporary", "repertoire"]


def test_genres_ignore_flamenco_musical_theatre():
    cur = goh._curriculum_text(_PASSION_AND_PRECISION)
    # Flamenco / Musical Theatre have no Genre enum, so they don't appear.
    assert goh._genres(cur) == ["classical", "pointe", "contemporary", "repertoire"]


def test_genres_default_classical():
    assert goh._genres("") == ["classical"]


# --- levels -------------------------------------------------------------------


def test_levels_span_beginner_to_advanced():
    assert goh._levels(goh._levels_text(_BALLET_AND_BEYOND)) == [
        "beginner",
        "intermediate",
        "advanced",
    ]


# --- sessions -----------------------------------------------------------------


def test_two_dated_sessions_from_list_set():
    sessions = goh._sessions(_BALLET_AND_BEYOND, date(2026, 7, 6), date(2026, 7, 31))
    assert [(s.start, s.end) for s in sessions] == [
        (date(2026, 7, 6), date(2026, 7, 17)),
        (date(2026, 7, 20), date(2026, 7, 31)),
    ]
    assert sessions[0].label is not None
    assert sessions[0].label.startswith("Session One")


def test_single_session_when_no_sub_list():
    sessions = goh._sessions(_PASSION_AND_PRECISION, date(2026, 8, 10), date(2026, 8, 20))
    assert [(s.start, s.end) for s in sessions] == [(date(2026, 8, 10), date(2026, 8, 20))]


# --- audition url -------------------------------------------------------------


def test_audition_url():
    url = goh._audition_url(_BALLET_AND_BEYOND)
    assert url is not None and url.startswith("https://www.eventbrite.ca/")
    assert goh._audition_url(_TORONTO_LINK) == "https://x/"


# --- end-to-end ---------------------------------------------------------------


def test_build_offerings_keeps_only_dated_intensives():
    offerings = goh._build_offerings(_RECORD, date(2026, 1, 1))
    # Two intensives kept; the children's camp + Toronto cross-link dropped.
    assert [o.id for o in offerings] == [
        "goh-ballet-academy/ballet-beyond-july-2026",
        "goh-ballet-academy/passion-precision-august-2026",
    ]


def test_ballet_and_beyond_offering():
    o = next(
        x
        for x in goh._build_offerings(_RECORD, date(2026, 1, 1))
        if x.id.endswith("ballet-beyond-july-2026")
    )
    assert o.title == "Ballet & Beyond – July International Summer Intensive"
    assert o.schedule.season == "2026"
    assert o.schedule.start == date(2026, 7, 6)
    assert o.schedule.end == date(2026, 7, 31)
    assert o.schedule.timezone == "America/Vancouver"
    assert o.age_range == {"min": 7, "max": None}
    assert o.genres == ["classical", "pointe", "contemporary", "repertoire"]
    assert len(o.schedule.sessions) == 2
    assert o.location is not None
    assert (o.location.city, o.location.country) == ("Vancouver", "CA")
    assert o.prices == []  # no tuition figure stated → none invented
    assert o.teachers == []  # Guest Instructors: TBA
    (req,) = o.application.requirements
    assert isinstance(req, VideoReq) and req.specificity == "unspecific"
    assert o.application.url is not None and o.application.url.startswith("https://www.eventbrite")


def test_passion_and_precision_offering():
    o = next(
        x
        for x in goh._build_offerings(_RECORD, date(2026, 1, 1))
        if x.id.endswith("passion-precision-august-2026")
    )
    assert o.schedule.start == date(2026, 8, 10)
    assert o.schedule.end == date(2026, 8, 20)
    assert o.age_range == {"min": 7, "max": None}
    assert len(o.schedule.sessions) == 1
