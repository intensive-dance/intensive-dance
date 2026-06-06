"""Unit tests for the Prix de Lausanne — Summer Intensive scraper.

These pin the regex parsing of the one server-rendered page: the single-month
course range, the birthdate-band → age-range derivation, the registration window
→ status logic (the closed≠cancelled IDR-24 case), the video requirement, the
CHF registration fee, and a no-date fallback. Inline strings, no network.

The HTML mirrors the live page's wording (verified 2026-06).
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import prix_de_lausanne_summer_intensive as pdl

# A trimmed slice of the live page's body text wrapped in minimal HTML.
HTML = """
<html><body>
<h1>Summer Intensive – International Preselection</h1>
<p>Discover. Train. Belong. The Summer Intensive – International Preselection is
an exceptional six-day programme created by the Prix de Lausanne for the most
promising young dancers of tomorrow. Held each July at the historic Beaulieu
Theatre in Lausanne, Switzerland, it offers a rare opportunity to train at the
highest level. Participants take part in intensive classical ballet classes and
contemporary coaching led by world-renowned teachers.</p>
<p>The 2026 Summer Intensive will take place from 6 to 11 July 2026.
Registration was open from 15 March to 15 April 2026.</p>
<p>Dancers must be born between 7 February 2008 and 6 February 2012. The summer
intensive is open to dancers of all nationalities. Registration will be open
from 15 March to 15 April 2026. Dancers must upload their video by 15 April
2026. The 1st registration fee* (CHF 150-.) must be paid by 15 April 2026.
Dancers will find out if they are selected by 5 May 2026.</p>
<p>*All registration and tuition fees are non-refundable.</p>
</body></html>
"""


def test_date_range_single_month():
    assert pdl._date_range("will take place from 6 to 11 July 2026.") == (
        date(2026, 7, 6),
        date(2026, 7, 11),
    )


def test_date_range_absent():
    assert pdl._date_range("dates to be announced") == (None, None)


def test_age_range_from_birthdate_band():
    # born 6 Feb 2012 (youngest) → 14 by the 6 Jul 2026 start; born 7 Feb 2008
    # (oldest) → 18. The Feb birthday is already past by July, so no -1.
    text = "from 6 to 11 July 2026. born between 7 February 2008 and 6 February 2012"
    assert pdl._age_range(text) == {"min": 14, "max": 18}


def test_age_range_absent_without_band():
    assert pdl._age_range("from 6 to 11 July 2026. open to all nationalities") is None


def test_registration_window():
    text = "Registration was open from 15 March to 15 April 2026."
    assert pdl._registration_window(text) == (date(2026, 3, 15), date(2026, 4, 15))


def test_status_closed_after_window():
    # Today after the close → closed (but the edition still takes place).
    assert pdl._status(date(2026, 3, 15), date(2026, 4, 15), date(2026, 6, 6)) == "closed"


def test_status_open_during_window():
    assert pdl._status(date(2026, 3, 15), date(2026, 4, 15), date(2026, 4, 1)) == "open"


def test_status_upcoming_before_window():
    assert pdl._status(date(2026, 3, 15), date(2026, 4, 15), date(2026, 2, 1)) == "upcoming"


def test_status_none_when_window_unknown():
    assert pdl._status(None, None, date(2026, 6, 6)) is None


def test_video_deadline():
    assert pdl._video_deadline("must upload their video by 15 April 2026.") == date(2026, 4, 15)


def test_requirements_video_unspecific():
    reqs = pdl._requirements("Dancers must upload their video by 15 April 2026.")
    assert len(reqs) == 1
    assert reqs[0].type == "video"
    assert reqs[0].specificity == "unspecific"


def test_requirements_empty_when_no_video():
    assert pdl._requirements("Registration was open from 15 March to 15 April 2026.") == []


def test_prices_registration_fee_chf():
    prices = pdl._prices("The 1st registration fee* (CHF 150-.) must be paid by 15 April 2026.")
    assert len(prices) == 1
    assert prices[0].amount == 150.0
    assert prices[0].currency == "CHF"
    assert prices[0].includes == []


def test_prices_absent():
    assert pdl._prices("no fee mentioned here") == []


def test_genres():
    text = "intensive classical ballet classes and contemporary coaching with variations"
    assert pdl._genres(text) == ["classical", "contemporary", "repertoire"]


def test_build_offering_full():
    o = pdl._build_offering(HTML, today=date(2026, 6, 6))
    assert o is not None
    assert o.id == "prix-de-lausanne-summer-intensive/summer-intensive-2026"
    assert o.title == "Summer Intensive 2026"
    assert o.organization.slug == "prix-de-lausanne-summer-intensive"
    assert o.lifecycle == "scheduled"  # closed registration ≠ cancelled course
    assert o.schedule.start == date(2026, 7, 6)
    assert o.schedule.end == date(2026, 7, 11)
    assert o.schedule.timezone == "Europe/Zurich"
    assert o.age_range == {"min": 14, "max": 18}
    assert o.location is not None
    assert o.location.venue == "Beaulieu Theatre"
    assert o.location.city == "Lausanne"
    assert o.location.country == "CH"
    assert o.application.status == "closed"
    assert o.application.opens_at == date(2026, 3, 15)
    assert o.application.deadline == date(2026, 4, 15)
    assert [r.type for r in o.application.requirements] == ["video"]
    assert len(o.prices) == 1
    assert o.prices[0].currency == "CHF"
    assert "classical" in o.genres


def test_build_offering_open_window():
    # Mid-window scrape → status open; lifecycle still scheduled.
    o = pdl._build_offering(HTML, today=date(2026, 4, 1))
    assert o is not None
    assert o.application.status == "open"
    assert o.lifecycle == "scheduled"


def test_build_offering_none_without_dates():
    assert (
        pdl._build_offering("<html><body><p>coming soon</p></body></html>", date(2026, 6, 6))
        is None
    )
