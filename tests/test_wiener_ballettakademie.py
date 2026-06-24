"""Unit tests for the Wiener Ballettakademie scraper (base44 SPA, one page).

These pin the parsing of the rendered Intensive Ballet Masterclass page: the
single-month date span, the open-topped age band, the level pair, the curriculum
genres, the three EUR booking tiers (label / amount / deposit, including the
"from €" per-lesson tier), the named faculty with Vienna State Ballet / Opera
affiliations (including a *former* principal via a past-tenure parenthetical),
and the degraded-render guard. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import wiener_ballettakademie as wba

# A faithful slice of the rendered DOM as `_text` would emit it: one visible
# source line per line, already whitespace-cleaned.
PAGE = "\n".join(
    [
        "Intensive Ballet Masterclass 2026",
        "Vienna · 24 – 30 August 2026",
        "Suitable for ages 15 and above",
        "Open to advanced students & professionals",
        "Daily Classical Ballet, Repertoire & Pas de Deux",
        "Pointe & Contemporary classes",
        "Meet the Artists",
        "Galina Skuratova",
        "Prima Ballerina · Honoured Artist of Russia",
        "Maria Yakovleva",
        "First Soloist · Vienna State Ballet",
        "Iryna Tsymbal",
        "Principal Dancer · Vienna State Opera (2005–2020)",
        "Pricing & Registration",
        "Full Masterclass",
        "€ 890",
        "Deposit to secure: € 200",
        "Full Masterclass + Individual Lessons",
        "€ 1,290",
        "Deposit to secure: € 300",
        "Individual Lessons Only",
        "from € 150",
        "Deposit to secure: € 150",
    ]
)


def test_build_offering_core_fields():
    o = wba._build_offering(PAGE)
    assert o.id == "wiener-ballettakademie/intensive-ballet-masterclass-2026"
    assert o.title == "Intensive Ballet Masterclass 2026"
    assert o.schedule.season == "2026"
    assert (o.schedule.start, o.schedule.end) == (date(2026, 8, 24), date(2026, 8, 30))
    assert o.age_range == {"min": 15, "max": None}
    assert o.level == ["advanced", "professional"]
    assert set(o.genres) == {"classical", "repertoire", "pointe", "contemporary"}
    assert o.location is not None and o.location.city == "Vienna"


def test_dates_single_month_span():
    assert wba._dates("Vienna · 24 – 30 August 2026", "2026")[:2] == (
        date(2026, 8, 24),
        date(2026, 8, 30),
    )


def test_age_open_topped():
    assert wba._age_range("ages 15 and above") == {"min": 15, "max": None}
    assert wba._age_range("ages 12+") == {"min": 12, "max": None}


def test_three_price_tiers_with_deposits():
    prices = wba._prices(PAGE)
    rows = [(p.label, p.amount, p.currency, p.includes) for p in prices]
    assert rows == [
        ("Full Masterclass", 890.0, "EUR", ["tuition"]),
        ("Full Masterclass + Individual Lessons", 1290.0, "EUR", ["tuition"]),
        ("Individual Lessons Only", 150.0, "EUR", ["tuition"]),
    ]
    assert "Deposit to secure: €200" in (prices[0].notes or "")
    # The per-lesson tier is flagged "from".
    assert (prices[2].notes or "").startswith("From €150 per lesson")


def test_teacher_affiliations_current_and_former():
    teachers = {t.name: t for t in wba._teachers(PAGE)}
    assert set(teachers) == {"Galina Skuratova", "Maria Yakovleva", "Iryna Tsymbal"}
    # No org named in the credential → names-only (no invented affiliation).
    assert teachers["Galina Skuratova"].affiliations == []
    # Current Vienna State Ballet soloist.
    yak = teachers["Maria Yakovleva"].affiliations[0]
    assert (yak.organization, yak.role, yak.current) == (
        "Wiener Staatsballett",
        "First Soloist",
        True,
    )
    # Past tenure "(2005–2020)" → current=False.
    tsy = teachers["Iryna Tsymbal"].affiliations[0]
    assert (tsy.organization, tsy.current) == ("Vienna State Opera", False)


def test_degraded_render_raises():
    # A render missing the edition marker must raise, not return an empty offering,
    # so a transient blip can't wipe the committed edition.
    with pytest.raises(ValueError):
        wba._build_offering("Just a navigation menu with no masterclass marker.")
