"""Unit tests for the Prague Ballet Intensive scraper (WordPress REST + title).

These pin the bespoke single-month date regex (year stated *before* the month),
the age band ("between"/"aged" wording), the two EUR tuition tiers (with their
"1 660" inner-space grouping), the curriculum genres, the audition requirement
set with its named arabesque pose, and the venue extraction. Inline strings, no
network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq
from intensive_dance.scrapers import prague_ballet_intensive as pbi

# A faithful trim of the real WP `content.rendered` bodies + the home <title>.
_TITLE = "Prague Ballet Intensive – Summer 2026, August 10th – 22nd"
_ABOUT = (
    "PBI provides a high quality pre-professional and professional international "
    "ballet coaching program. Participants spend 12 working days of ballet class, "
    "variations, pas de deux and contemporary concluded with a yoga class each "
    "evening. PBI is for (pre)professional and professional dancers aged 15 – 35 "
    "years old."
)
_APPLY = (
    "To audition for PBI Summer 2026, please fill out the form on our website. "
    "Include a short CV outlining your experiences and training along with your "
    "headshot, 1 CURRENT photo of yourself in first arabesque and 1 CURRENT "
    "ballet photo of your choice. All participants must be between 15 – 35 years "
    "of age."
)
_TUITION = (
    "Course tuition will amount 1 660 euros or 40 600 czk . One week tuition will "
    "amount 860 euros or 20 600 czk . A non refundable deposit of 200 euros."
)
_LOCATION = (
    "Two studios next to the subway. PBI summer course will be held at CONTEMPORARY "
    "at National House of Vinohrady . Náměstí Míru (Peace Square)."
)


def test_date_range_year_before_single_month():
    assert pbi._date_range(_TITLE) == (date(2026, 8, 10), date(2026, 8, 22))


def test_date_range_absent():
    assert pbi._date_range("Prague Ballet Intensive – Summer") == (None, None)


def test_age_range_from_apply_between():
    assert pbi._age_range(_APPLY) == {"min": 15, "max": 35}


def test_age_range_from_about_aged():
    assert pbi._age_range(_ABOUT) == {"min": 15, "max": 35}


def test_levels_pre_professional_and_professional():
    assert pbi._levels(_ABOUT) == ["pre-professional", "professional"]


def test_levels_pre_professional_only_not_double_counted():
    # "pre-professional" alone must not also register "professional".
    assert pbi._levels("a pre-professional program") == ["pre-professional"]


def test_genres_from_curriculum():
    assert pbi._genres(_ABOUT) == ["classical", "repertoire", "contemporary"]


def test_genres_default_classical():
    assert pbi._genres("an intensive of fun") == ["classical"]


def test_prices_two_eur_tiers_with_inner_space_grouping():
    prices = pbi._prices(_TUITION)
    assert [(p.amount, p.currency, p.label, p.includes) for p in prices] == [
        (1660.0, "EUR", "Full course tuition (two weeks)", ["tuition"]),
        (860.0, "EUR", "One week tuition", ["tuition"]),
    ]


def test_requirements_audition_set_with_named_arabesque():
    reqs = pbi._requirements(_APPLY)
    assert {r.type for r in reqs} == {"cv", "headshot", "photos"}
    photos = next(r for r in reqs if isinstance(r, PhotosReq))
    assert photos.specificity == "defined-poses"
    assert photos.poses == ["first arabesque"]
    assert photos.notes is not None and "freeform" in photos.notes


def test_requirements_freeform_when_no_named_pose():
    reqs = pbi._requirements("Include a ballet photo of your choice.")
    photos = next(r for r in reqs if isinstance(r, PhotosReq))
    assert photos.specificity == "freeform"
    assert photos.poses == []


def test_location_takes_named_venue_not_studio_label():
    loc = pbi._location(_LOCATION)
    assert loc.venue == "National House of Vinohrady"
    assert (loc.city, loc.country) == ("Prague", "CZ")


def test_build_offering_end_to_end():
    pages = {"about": _ABOUT, "apply": _APPLY, "tuition": _TUITION, "location": _LOCATION}
    home_html = f"<html><head><title>{_TITLE}</title></head><body></body></html>"
    offering = pbi._build_offering(home_html, pages)
    assert offering is not None
    assert offering.id == "prague-ballet-intensive/summer-intensive-2026"
    assert offering.schedule.start == date(2026, 8, 10)
    assert offering.schedule.end == date(2026, 8, 22)
    assert offering.age_range == {"min": 15, "max": 35}
    assert offering.organization.slug == "prague-ballet-intensive"
    assert (
        offering.location is not None and offering.location.venue == "National House of Vinohrady"
    )


def test_build_offering_none_without_dates():
    home_html = "<html><head><title>Prague Ballet Intensive</title></head><body></body></html>"
    assert pbi._build_offering(home_html, {"about": "", "apply": "", "tuition": ""}) is None
