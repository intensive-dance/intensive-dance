"""Unit tests for the Ballet Workshops Bucharest scraper (single Wix page).

These pin the regex/structural parsing of the one Ballet Summer Camp page — the
single-month date range (shared trailing year), the 9-18 age band with three
groups (one open-topped), the curriculum-driven genres, the €1100 fee, the
June-9th deadline resolved against the camp year, the structured teacher roster,
and the full `_build_offering` assembly. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from selectolax.parser import HTMLParser

from intensive_dance.scrapers import ballet_workshops_bucharest as bw

# A faithful slice of the live page (zero-width spaces inserted as Wix does it).
SAMPLE = """
<html><body>
<h2>Ballet Summer Camp</h2>
<h2>Edition VII | 9-19 July 2026 ​Bucharest</h2>
<div class="info-member info-element-title">Alejandro Parente</div>
<div class="info-member info-element-description">International Guest Ballet Teacher</div>
<div class="info-member info-element-title">Marina Minoiu</div>
<div class="info-member info-element-description">Ballet Coordinator at the National Musical
and Operetta Theater „Ion Dacian” Ballet Teacher at Casa de Balet</div>
<div class="info-member info-element-title">Daria Stănciulescu</div>
<div class="info-member info-element-description">First Artist with Birmingham Royal Ballet</div>
<p>The workshop is aimed at students aged 9 to 18 who wish to enrich their level.</p>
<p>The classes will be structured into three age groups suited to the students'
age levels: 9-11 years, 12-14 years, and 15+ years.</p>
<p>Classes Classical Technique Pointe Technique Repertoire: Female / Male Variations
and Group Contemporary Dance</p>
<p>Accommodation We provide assistance for lodging close to the dance school.</p>
<p>You can sign up for BSC by completing the online registration form.</p>
<p>PARTICIPATION FEES ​€1100 Full workshop and Final Showcase Gala The
registration deadline is June 9th. Discounts do not stack</p>
</body></html>
"""


def test_date_range_single_month_shared_year():
    assert bw._date_range("Edition VII | 9-19 July 2026 Bucharest") == (
        date(2026, 7, 9),
        date(2026, 7, 19),
    )


def test_date_range_absent():
    assert bw._date_range("no dated edition announced yet") == (None, None)


def test_age_range_nine_to_eighteen():
    assert bw._age_range("students aged 9 to 18 who wish to enrich") == {"min": 9, "max": 18}


def test_age_range_absent():
    assert bw._age_range("a classical summer camp") is None


def test_sessions_three_groups_open_top():
    sessions = bw._sessions("age groups: 9-11 years, 12-14 years, and 15+ years")
    assert [(s.label, s.age_range) for s in sessions] == [
        ("9-11 years", {"min": 9, "max": 11}),
        ("12-14 years", {"min": 12, "max": 14}),
        ("15+ years", {"min": 15}),  # open-ended upper bound
    ]


def test_genres_from_curriculum():
    text = "Classical Technique Pointe Technique Repertoire Variations Contemporary Dance"
    assert bw._genres(text) == ["classical", "pointe", "repertoire", "contemporary"]


def test_price_fee_tuition_and_gala():
    prices = bw._prices("PARTICIPATION FEES €1100 Full workshop and Final Showcase Gala The")
    assert len(prices) == 1
    p = prices[0]
    assert p.amount == 1100.0
    assert p.currency == "EUR"
    assert p.includes == ["tuition", "performance"]
    assert "Full workshop" in (p.label or "")


def test_deadline_resolved_against_camp_year():
    assert bw._deadline("The registration deadline is June 9th.", 2026) == date(2026, 6, 9)


def test_deadline_absent():
    assert bw._deadline("apply via the registration form", 2026) is None


def test_teachers_paired_structurally():
    teachers = bw._teachers(HTMLParser(SAMPLE))
    names = [(t.name, t.role) for t in teachers]
    assert ("Alejandro Parente", "International Guest Ballet Teacher") in names
    assert ("Daria Stănciulescu", "First Artist with Birmingham Royal Ballet") in names
    assert len(teachers) == 3


def test_build_offering_end_to_end():
    o = bw._build_offering(SAMPLE)
    assert o is not None
    assert o.id == "ballet-workshops-bucharest/summer-camp-2026"
    assert o.title == "Ballet Summer Camp 2026"
    assert o.schedule.start == date(2026, 7, 9)
    assert o.schedule.end == date(2026, 7, 19)
    assert o.schedule.timezone == "Europe/Bucharest"
    assert o.age_range == {"min": 9, "max": 18}
    assert o.genres == ["classical", "pointe", "repertoire", "contemporary"]
    assert o.lifecycle == "scheduled"
    assert o.location is not None and o.location.country == "RO"
    assert o.application.deadline == date(2026, 6, 9)
    assert o.application.requirements == []  # no audition brief stated
    assert len(o.teachers) == 3
    assert len(o.prices) == 1 and o.prices[0].amount == 1100.0


def test_build_offering_returns_none_without_dates():
    assert bw._build_offering("<html><body><p>coming soon</p></body></html>") is None


# --- Winter Camp --------------------------------------------------------------

WINTER_SAMPLE = """
<html><body>
<h2>BALLET WINTER CAMP</h2><h2>2-6 January 2026 ​Bucharest</h2>
<div class="info-member info-element-title">Lynne Charles</div>
<div class="info-member info-element-description">Artistic Director English National
Ballet School Founder and Creator of 4 Pointe</div>
<p>Organized by Casa de Balet, the workshop participants will have access to studies of
classical ballet, duet, classical repertoire, contemporary dance and more.</p>
<p>The workshop is for young students aged between 9 and 18 years. You can sign up for
BWC by completing the online registration form.</p>
<p>PARTICIPATION FEES ​ALL LEVELS €600 The registration deadline is DECEMBER 22 . Full
payment or a 30% deposit ensures the reservation.</p>
</body></html>
"""


def test_age_range_between_form():
    assert bw._age_range("students aged between 9 and 18 years") == {"min": 9, "max": 18}


def test_winter_genres_scoped_to_curriculum_not_teacher_bio():
    # "4 Pointe" is in a teacher bio, not the winter curriculum — it must not leak.
    text = bw._page_text(WINTER_SAMPLE)
    assert bw._winter_genres(text) == ["classical", "repertoire", "contemporary"]


def test_winter_price_band_before_figure():
    prices = bw._prices("PARTICIPATION FEES ALL LEVELS €600 The registration deadline is")
    assert len(prices) == 1
    assert prices[0].amount == 600.0
    assert prices[0].includes == ["tuition"]  # no gala/showcase → tuition only
    assert prices[0].label == "All levels"


def test_deadline_rolls_back_across_year_boundary():
    # A December deadline for a January camp belongs to the prior calendar year.
    assert bw._deadline_rollback(
        "The registration deadline is DECEMBER 22.", date(2026, 1, 2)
    ) == date(2025, 12, 22)
    # A same-side deadline keeps the camp year.
    assert bw._deadline_rollback(
        "The registration deadline is June 9th.", date(2026, 7, 9)
    ) == date(2026, 6, 9)


def test_build_winter_end_to_end():
    o = bw._build_winter(WINTER_SAMPLE)
    assert o is not None
    assert o.id == "ballet-workshops-bucharest/winter-camp-2026"
    assert o.title == "Ballet Winter Camp 2026"
    assert o.schedule.start == date(2026, 1, 2)
    assert o.schedule.end == date(2026, 1, 6)
    assert o.age_range == {"min": 9, "max": 18}
    assert o.genres == ["classical", "repertoire", "contemporary"]
    assert o.application.deadline == date(2025, 12, 22)
    assert o.application.requirements == []
    assert len(o.prices) == 1 and o.prices[0].amount == 600.0
    assert [t.name for t in o.teachers] == ["Lynne Charles"]


# --- Masterclasses ------------------------------------------------------------

MASTERCLASS_SAMPLE = """
<html><body>
<p>MASTERS &amp; WORKSHOPS UPCOMING Marco Laudani Contemporary Dance Masterclass
06-08 March 2026 Christopher Powney Ballet Masterclass 21-22 March 2026 Soon more
guests TBA</p>
<p>Past events: Old Guest Ballet Masterclass 01-02 February 2020</p>
</body></html>
"""


def test_build_masterclasses_one_per_guest():
    offerings = bw._build_masterclasses(MASTERCLASS_SAMPLE)
    by_id = {o.id: o for o in offerings}
    assert set(by_id) == {
        "ballet-workshops-bucharest/masterclass-marco-laudani-2026",
        "ballet-workshops-bucharest/masterclass-christopher-powney-2026",
    }
    marco = by_id["ballet-workshops-bucharest/masterclass-marco-laudani-2026"]
    assert marco.title == "Marco Laudani — Contemporary Dance Masterclass"
    assert marco.genres == ["contemporary"]
    assert marco.schedule.start == date(2026, 3, 6)
    assert marco.schedule.end == date(2026, 3, 8)
    assert [t.name for t in marco.teachers] == ["Marco Laudani"]

    powney = by_id["ballet-workshops-bucharest/masterclass-christopher-powney-2026"]
    assert powney.genres == ["classical"]  # "Ballet Masterclass" → default classical
    assert powney.schedule.start == date(2026, 3, 21)
    assert powney.schedule.end == date(2026, 3, 22)


def test_build_masterclasses_ignores_dates_outside_upcoming_block():
    # The past-event "01-02 February 2020" sits after "Soon more guests / TBA",
    # so it is outside the UPCOMING segment and must not become an Offering.
    offerings = bw._build_masterclasses(MASTERCLASS_SAMPLE)
    assert all("2020" not in o.id for o in offerings)


def test_build_masterclasses_empty_without_upcoming_block():
    assert bw._build_masterclasses("<html><body><p>no masterclasses listed</p></body></html>") == []
