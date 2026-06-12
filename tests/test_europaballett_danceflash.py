"""Unit tests for the Europaballett "Danceflash" summer-intensive scraper.

Danceflash is a plain static-HTML page. These pin the judgement calls a hash
check can't catch: the PARTICIPATION-FEE block splitting one dated edition into
two age-group Offerings (distinct ages/hours/fees), the German worded day span
("04. Juli - 11. Juli 2026"), the early-bird fee captured in the Price note, the
multi-genre keyword match, and fail-open behaviour when a fee row has no early
bird or the page carries no parseable date. Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import europaballett_danceflash as eb

# Mirrors the live page: a worded day span, the two-row PARTICIPATION-FEE block
# (each age group with its own daily hours + early-bird parenthetical), and the
# curriculum/faculty prose that carries the genre keywords.
_HTML = """
<html><body>
<h1>Danceflash</h1>
<p>Der Sommerworkshop findet von 04. Juli - 11. Juli 2026 statt.</p>
<h2>Teilnahmegebühr</h2>
<p>5-12 Jährige täglich von 09:30 - 14:30 Uhr € 300,- (Early bird bis 31.05. € 280,-)</p>
<p>13-26 Jährige täglich von 09:30 - 16:00 Uhr € 400,- (Early bird bis 31.05. € 380,-)</p>
<h2>Wochenplan</h2>
<p>Classical Training, Balanchine technique, Repertoire, Pointe (Spitze),
contemporary, Jazz und Hip-Hop.</p>
<p>Abschlussgala am 12. Juli.</p>
</body></html>
"""


def test_two_age_group_offerings() -> None:
    offerings = eb._build_offerings(_HTML)
    assert len(offerings) == 2

    juniors, seniors = offerings
    assert juniors.age_range == {"min": 5, "max": 12}
    assert seniors.age_range == {"min": 13, "max": 26}

    assert juniors.schedule.start == date(2026, 7, 4)
    assert juniors.schedule.end == date(2026, 7, 11)
    assert juniors.schedule.season == "2026"

    assert juniors.prices[0].amount == 300.0
    assert juniors.prices[0].currency == "EUR"
    assert juniors.prices[0].includes == ["tuition"]
    assert juniors.prices[0].notes == "Early bird: € 280"
    assert seniors.prices[0].amount == 400.0
    assert seniors.prices[0].notes == "Early bird: € 380"

    # distinct daily hours land in the per-group schedule notes
    assert "09:30–14:30" in (juniors.schedule.notes or "")
    assert "09:30–16:00" in (seniors.schedule.notes or "")

    # multi-genre match from the curriculum prose; Jazz/Hip-Hop have no enum value
    assert set(juniors.genres) == {
        "classical",
        "contemporary",
        "neoclassical",
        "repertoire",
        "pointe",
    }

    # open enrollment — no audition gate stated
    assert juniors.application is not None
    assert juniors.application.requirements == []


def test_fee_row_without_early_bird() -> None:
    html = (
        "<html><body>"
        "<p>von 04. Juli - 11. Juli 2026</p>"
        "<p>5-12 Jährige täglich von 09:30 - 14:30 Uhr € 300,-</p>"
        "</body></html>"
    )
    offerings = eb._build_offerings(html)
    assert len(offerings) == 1
    assert offerings[0].prices[0].amount == 300.0
    assert offerings[0].prices[0].notes is None


def test_missing_dates_fails_open() -> None:
    html = "<html><body><p>5-12 Jährige täglich von 09:30 - 14:30 Uhr € 300,-</p></body></html>"
    offerings = eb._build_offerings(html)
    assert len(offerings) == 1
    assert offerings[0].schedule.start is None
    assert offerings[0].schedule.end is None
    assert offerings[0].schedule.season == "2026"
