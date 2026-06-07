"""Unit tests for the Stage International de Danse Charles Jude scraper.

The source is a French WPBakery page (`content.rendered`). These pin the
judgement calls a hash check can't catch: the "6-18 Juillet 2026" French
single-month day-range, the open-access `open` level + "à partir de 8 ans"
open-topped age band, the two per-duration price ladders ("1 semaine" /
"2 semaine") plus the membership fee, the two labelled weekly sessions, the
`NoneReq` (open-access, no audition) requirement, and a missing-dates fall-open.
Inline shortcode HTML mirroring the live body — no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import NoneReq
from intensive_dance.scrapers import stage_charles_jude as scj

# Mirrors the live body: the dated heading + address, the open-access blurb, the
# two price tabs (1 semaine / 2 semaine), the three levels, and the deposit text.
# WPBakery wraps attribute values in curly quotes (»…») exactly as the API serves
# them; `wp.plain_text` strips the shortcodes, so the prose is what matters.
_RENDERED = """
<p>[vc_column_text el_class= »date »] 6-18 Juillet 2026 [/vc_column_text]
[vc_column_text el_class= »address »] École Nationale de Danse de Marseille
20 bd de Gabes Marseille [/vc_column_text]
[vc_column_text]Ce stage est accessible aux enfants et adultes amateurs ou
professionnels désirant profiter de l’excellence des professeurs.[/vc_column_text]
[vc_tta_section title= »1 semaine »][vc_column_text]
1 cours/jour 210€ 2 cours/jour 350€ 3 cours/jour 490€ cours illimités 700€
cours à l’unité 40€ (+ 15€ en adhésion sur chaque somme)[/vc_column_text][/vc_tta_section]
[vc_tta_section title= »2 semaine »][vc_column_text]
1 cours/jour 400€ 2 cours/jour 680€ 3 cours/jour 950€ cours illimités 1350€
cours à l’unité 40€ (+ 15€ en adhésion sur chaque somme)[/vc_column_text][/vc_tta_section]
[vc_column_text]Élementaire (à partir de 8 ans) Intermédiaire (à partir de 11 ans)
Avancé-Pro (à partir de 14 ans)[/vc_column_text]
[vc_column_text]Pour valider votre pré-inscription, 50% du montant total devra être
payé. Le solde restant devra être réglé au plus tard sur place le dimanche 5 juillet
entre 17h et 19h pour la 1ere semaine ou le dimanche 12 juillet entre 17h et 19h
pour la 2eme semaine à l’Ecole Nationale de Danse de Marseille.[/vc_column_text]</p>
"""

# Mirrors the /inscription page body (scraper’s second fetch): the dress-code
# paragraph that drives genre matching. Genres come from this page, not the main
# body, because only /inscription names the actual class types (classique /
# contemporain) without bio prose that leaks "pointes".
_INSCRIPTION = (
    "Pour les filles – collant rose pour le classique / "
    "collant noir sans pied pour le contemporain. "
    "Les filles travaillent les pointes. "
    "Laure Muret effectue sa formation de danse classique. "
    "Elle donne des cours de techniques, de pointes et de transmission."
)


def test_build_offering_happy_path() -> None:
    offering = scj._build_offering(_RENDERED, _INSCRIPTION)
    assert offering is not None

    assert offering.id == "stage-charles-jude/summer-stage-2026"
    assert offering.title == "Stage International de Danse Charles Jude 2026"
    assert offering.schedule.season == "2026"
    assert offering.schedule.start == date(2026, 7, 6)
    assert offering.schedule.end == date(2026, 7, 18)
    assert offering.schedule.timezone == "Europe/Paris"
    assert offering.schedule.notes == "6-18 Juillet 2026"

    assert offering.location is not None
    assert offering.location.venue == "École Nationale de Danse de Marseille"
    assert offering.location.city == "Marseille"
    assert offering.location.country == "FR"


def test_open_access_level_and_open_topped_age() -> None:
    offering = scj._build_offering(_RENDERED, _INSCRIPTION)
    assert offering is not None
    # Open-access stage: `open` level, no audition.
    assert offering.level == ["open"]
    # Lowest stated threshold (8) with a null upper bound (adults attend).
    assert offering.age_range == {"min": 8}


def test_requirements_are_none_req() -> None:
    offering = scj._build_offering(_RENDERED, _INSCRIPTION)
    assert offering is not None
    reqs = offering.application.requirements
    assert len(reqs) == 1
    assert isinstance(reqs[0], NoneReq)
    assert offering.application.url == "https://stagedansecj.com/inscription"
    assert offering.application.notes is not None
    assert "50%" in offering.application.notes


def test_genres_from_dress_code_wording() -> None:
    offering = scj._build_offering(_RENDERED, _INSCRIPTION)
    assert offering is not None
    # Dress-code line "collant rose pour le classique / collant noir pour le
    # contemporain" drives genre matching. "pointes" appears only in Laure
    # Muret's bio and must NOT be derived from it.
    assert offering.genres == ["classical", "contemporary"]


def test_pointe_not_derived_from_teacher_bio() -> None:
    # Laure Muret's bio contains "cours de techniques, de pointes et de
    # transmission" — this must not trigger the pointe genre.
    # The dress-code line (classique/contemporain) must be present to ensure
    # the correct genres are still derived, while the bio "pointes" is ignored.
    text = (
        "collant rose pour le classique / collant noir sans pied pour le contemporain. "
        "Laure Muret effectue sa formation de danse classique. "
        "Elle donne des cours de techniques, de pointes et de transmission."
    )
    genres = scj._genres(text)
    assert "pointe" not in genres
    assert "classical" in genres
    assert "contemporary" in genres


def test_two_weekly_sessions() -> None:
    offering = scj._build_offering(_RENDERED, _INSCRIPTION)
    assert offering is not None
    sessions = offering.schedule.sessions
    assert [s.label for s in sessions] == ["Semaine 1", "Semaine 2"]
    # No fabricated per-week calendar split — only the source's balance dates.
    assert all(s.start is None and s.end is None for s in sessions)
    assert sessions[0].notes is not None and "5 juillet" in sessions[0].notes
    assert sessions[1].notes is not None and "12 juillet" in sessions[1].notes


def test_price_ladders_by_duration_plus_membership() -> None:
    offering = scj._build_offering(_RENDERED, _INSCRIPTION)
    assert offering is not None
    by_label = {p.label: p for p in offering.prices}

    # One-week ladder.
    assert by_label["1 semaine — 1 cours/jour"].amount == 210.0
    assert by_label["1 semaine — cours illimités"].amount == 700.0
    # Two-week ladder is attributed to the right tab, not the one-week one.
    assert by_label["2 semaines — 1 cours/jour"].amount == 400.0
    assert by_label["2 semaines — cours illimités"].amount == 1350.0
    # Drop-in and membership.
    assert by_label["1 semaine — cours à l’unité"].amount == 40.0
    assert by_label["Adhésion"].amount == 15.0

    assert all(p.currency == "EUR" for p in offering.prices)
    # The membership is a single line, not duplicated per tab.
    assert sum(1 for p in offering.prices if p.label == "Adhésion") == 1
    # Tuition fees carry the tuition include; the membership does not.
    assert by_label["1 semaine — 1 cours/jour"].includes == ["tuition"]
    assert by_label["Adhésion"].includes == []


def test_missing_dates_returns_none() -> None:
    # No parseable dated edition → fail open (no Offering invented).
    rendered = "<p>[vc_column_text]Le stage revient bientôt à Marseille.[/vc_column_text]</p>"
    assert scj._build_offering(rendered) is None


def test_french_date_range_helper() -> None:
    start, end = scj._date_range("Stage du 6-18 Juillet 2026 à Marseille")
    assert start == date(2026, 7, 6)
    assert end == date(2026, 7, 18)
    # An accented month name parses too.
    start, end = scj._date_range("20-22 décembre 2025")
    assert start == date(2025, 12, 20)
    assert end == date(2025, 12, 22)
