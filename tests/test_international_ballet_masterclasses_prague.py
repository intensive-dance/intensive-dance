"""Unit tests for the International Ballet Masterclasses Prague scraper.

The provider runs two summer programmes in Prague (senior + junior); these pin
each helper against inline snippets mirroring the live WordPress page bodies, and
run the full `_build_offerings` end to end. No network.

Edge cases pinned: the fees page carries a stale "2025" typo on the Week 1 range
(we ignore the inline year and stamp the season from the two-week range), Week 2
spans two months ("27th July – 1st August"), prices are quoted in both GBP and
EUR with/without accommodation, and the junior faculty line mixes names with
parenthetical affiliations and filler ("once again the very popular …").
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import PhotosReq
from intensive_dance.scrapers import international_ballet_masterclasses_prague as p

# --- inline snippets mirroring the live page bodies ---------------------------

_FEES = (
    "One Week Intensive Course Note: to see who is teaching in which week, please see the "
    "'Classes' page. Week 1: 20th -25th July 2025: Arriving Sunday 19th July 2026, leaving "
    "Sunday 26th July 2026 or Week 2: 27th July – 1st August 2026: Arriving Sunday 26th July "
    "2026, leaving Sunday 2nd August 2026 Package fee *, including accommodation: £1720.00 "
    "(sterling) or €2000.00 (euro) Course only fee , no accommodation: £1100 (sterling) or "
    "€1300 (euro) Two Week Intensive Course 20th July – 1st August 2026: Arriving on Sunday "
    "19th July 2026, and leaving on Sunday 2nd August 2026 Package fee* , including "
    "accommodation: £2750 (sterling) or €3220 (euro) Course only fee , no accommodation: "
    "£1950 (sterling) or €2300 (euro) A non-returnable deposit of £250 (pounds sterling) or "
    "€300 (Euro) will be required, but not until you have received confirmation that you "
    "have been accepted on to the course. The fee for the course option of your choice must "
    "be paid in full by June 1st 2026 or it will be assumed that you will not be attending."
)

_CLASSES = (
    "Schedule: Please note that some teachers are available in week 1 or week 2 only. "
    "Teachers in Week One (20th – 25th July 2026): Daria Klimentová, Laurretta Summerscales, "
    "Jakob Feyferlik, Ayaka Fuji, Mario Radacovsky, Christopher Powney, Ondrej Vinklat "
    "Teachers in Week Two (27th July – 1st August 2026): Daria Klimentová, Liudmila "
    "Konovalova, Daichi Ikarashi, Tamas Solymosi, Christopher Hampson, Tereza Podarilová, "
    "Jan Kodet A typical day at the Masterclasses 10.00 – 11.30 General Class 15.00-16.30 "
    "Contemporary/Pas de deux"
)

_APPLY = (
    "A note about level: The level for these masterclasses is described as advanced/"
    "professional. This means that you may be: professional, semi-professional or have "
    "completed at least one year in full-time training for a career in dance, and have "
    "reached your 16th birthday by the beginning of the course. MINIMUM AGE IS 16 Please "
    "attach a reference from your teacher (if a student) and a photograph of yourself in a "
    "normal ballet position (1st arabesque is best)"
)

_TC = (
    "TERMS AND CONDITIONS Candidates will be selected from the applications submitted. "
    "Applications cannot be accepted without an accompanying photograph. Closing date for "
    "the applications is 14th July. However, places are limited. Deposits are non-refundable."
)

_JUNIOR = (
    "Welcome to the Junior Masterclasses for Summer 2026. International Ballet Masterclasses "
    "in Prague are very pleased to be able to announce the fourth year for junior students, "
    "aged 13-15 years old, led by the world famous Prima Ballerina and ex Royal Ballet "
    "School teacher, Daria Klimentová. Joining her in 2026 will be Simona Ferrazza (from "
    "Dutch National Ballet School), Tim Almaas (Director of Norwegian National Ballet "
    "School, Oslo), Ioanna Avraam (Principal Dancer Vienna State Ballet) and once again the "
    "very popular Royal Ballet Dancer, Denilson Almeida. The dates for 2026 will be from the "
    "3rd -7 th August 2026 inclusive. 10.00-11.30 General Class 12.00-13.15 Boys Variation "
    "15.00-16.30 Girls and Boys repertoire / Contemporary The price of the course is £750.00 "
    "(seven hundred and fifty pounds sterling) or €900.00 (nine hundred euro). To apply fill "
    "out the below form, and submit with a good photograph, preferably in 1st Arabesque."
)


# --- senior session parsing ---------------------------------------------------


def test_senior_sessions_both_weeks_ignoring_stale_year():
    sessions = p._senior_sessions(_FEES)
    # Week 1's inline "2025" typo is ignored; the season comes from the two-week
    # range's 2026 closing year. Week 2 spans two months.
    assert [(s.label, s.start, s.end) for s in sessions] == [
        ("Week 1", date(2026, 7, 20), date(2026, 7, 25)),
        ("Week 2", date(2026, 7, 27), date(2026, 8, 1)),
    ]


def test_senior_sessions_absent_without_two_week_anchor():
    # No two-week range → no reliable year → emit nothing rather than guess.
    assert p._senior_sessions("Week 1: 20th -25th July") == []


def test_senior_age_open_upper_bound():
    assert p._senior_age(_APPLY) == {"min": 16}  # null upper bound


def test_senior_level():
    assert p._senior_level(_APPLY) == ["professional", "pre-professional"]


def test_senior_teachers_per_week_roles():
    teachers = p._senior_teachers(_CLASSES)
    week_one = [t.name for t in teachers if "Week One" in (t.role or "")]
    week_two = [t.name for t in teachers if "Week Two" in (t.role or "")]
    assert week_one[0] == "Daria Klimentová"
    assert week_one[-1] == "Ondrej Vinklat"
    assert len(week_one) == 7
    assert week_two[0] == "Daria Klimentová"
    assert week_two[-1] == "Jan Kodet"
    assert len(week_two) == 7


def test_senior_prices_both_currencies_and_options():
    prices = p._senior_prices(_FEES)
    keyed = {(pr.currency, pr.label): (pr.amount, pr.includes) for pr in prices}
    assert keyed[("EUR", "One-week course — package, incl. accommodation")] == (
        2000.0,
        ["tuition", "accommodation"],
    )
    assert keyed[("GBP", "One-week course — course only")] == (1100.0, ["tuition"])
    assert keyed[("EUR", "Two-week course — package, incl. accommodation")] == (
        3220.0,
        ["tuition", "accommodation"],
    )
    assert keyed[("GBP", "Two-week course — course only")] == (1950.0, ["tuition"])
    # Eight prices: 2 options x 2 fee kinds x 2 currencies.
    assert len(prices) == 8


def test_senior_closing_date_stamps_edition_year():
    # The T&C wording carries no year; we stamp the edition's.
    assert p._closing_date(_TC, 2026) == date(2026, 7, 14)


def test_senior_apply_note_combines_deposit_and_payment():
    note = p._senior_apply_note(_FEES)
    assert note is not None
    assert "non-returnable deposit" in note
    assert "paid in full by June 1st 2026" in note


def test_senior_requirements_photo_with_defined_pose():
    reqs = p._senior_requirements(_APPLY)
    photo = next(r for r in reqs if isinstance(r, PhotosReq))
    assert photo.specificity == "defined-poses"
    assert photo.poses == ["first arabesque"]


def test_senior_genres():
    assert p._genres(_CLASSES) == ["classical", "contemporary"]


# --- junior parsing -----------------------------------------------------------


def test_junior_dates_single_month():
    assert p._junior_dates(_JUNIOR) == (date(2026, 8, 3), date(2026, 8, 7))


def test_junior_age_bounded():
    assert p._junior_age(_JUNIOR) == {"min": 13, "max": 15}


def test_junior_teachers_strip_affiliations_and_filler():
    teachers = p._junior_teachers(_JUNIOR)
    assert ("Daria Klimentová", "Lead Teacher") == (teachers[0].name, teachers[0].role)
    guests = [t.name for t in teachers if t.role == "Guest Teacher"]
    assert guests == ["Simona Ferrazza", "Tim Almaas", "Ioanna Avraam", "Denilson Almeida"]


def test_junior_prices_both_currencies():
    prices = p._junior_prices(_JUNIOR)
    assert {(pr.currency, pr.amount) for pr in prices} == {("EUR", 900.0), ("GBP", 750.0)}
    assert all(pr.includes == ["tuition"] for pr in prices)


def test_junior_requirements_photo():
    reqs = p._junior_requirements()
    photo = next(r for r in reqs if isinstance(r, PhotosReq))
    assert photo.poses == ["first arabesque"]


# --- end to end ---------------------------------------------------------------


def test_build_offerings_two_programmes():
    senior_html = {
        "options-fees": f"<div>{_FEES}</div>",
        "classes": f"<div>{_CLASSES}</div>",
        "how-to-apply": f"<div>{_APPLY}</div>",
        "tcs-and-scholarship": f"<div>{_TC}</div>",
    }
    offerings = p._build_offerings(senior_html, f"<div>{_JUNIOR}</div>")
    assert len(offerings) == 2

    senior, junior = offerings
    assert senior.id == "international-ballet-masterclasses-prague/summer-masterclasses-2026"
    assert senior.title == "Summer Masterclasses 2026"
    assert senior.schedule.start == date(2026, 7, 20)
    assert senior.schedule.end == date(2026, 8, 1)
    assert len(senior.schedule.sessions) == 2
    assert senior.age_range == {"min": 16}
    assert senior.application.deadline == date(2026, 7, 14)
    assert len(senior.prices) == 8
    assert senior.location is not None
    assert senior.location.city == "Prague"
    assert senior.location.country == "CZ"

    assert junior.id == "international-ballet-masterclasses-prague/junior-masterclasses-2026"
    assert junior.schedule.start == date(2026, 8, 3)
    assert junior.age_range == {"min": 13, "max": 15}
    assert junior.application.requirements[0].type == "photos"


def test_build_offerings_skips_undated_senior():
    # No parseable senior dates → only the junior Offering is emitted.
    offerings = p._build_offerings(
        {"options-fees": "<div>fees TBA</div>", "classes": "", "how-to-apply": ""},
        f"<div>{_JUNIOR}</div>",
    )
    assert [o.title for o in offerings] == ["Junior Masterclasses 2026"]
