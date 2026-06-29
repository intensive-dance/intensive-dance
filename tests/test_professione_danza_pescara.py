"""Unit tests for the Professione Danza Pescara Summer Intensive School scraper.

Pin the two-track split (children/youth → two Offerings), Italian per-week dates
with the year read from the header, curriculum-scoped genres (pointe only for the
youth track; no repertoire leak from a faculty 'Forsythe' bio), the split-line
fee parsing ("Euro\\n100,00\\n(senza stage)"), names-only faculty (incl. a
dash-less 4th-week bio), and the fail-open raise. Inline HTML, no network.
"""

from __future__ import annotations

from datetime import date

import pytest

from intensive_dance.scrapers import professione_danza_pescara as p

# Mirrors the SiteOrigin-rendered page: header carries the only year; each track
# has its curriculum sentence, four week blocks, a faculty list (one dash-less),
# and a Costi block whose senza-stage amount is split across lines (children).
_HTML = """
<html><body>
<h2>SUMMER INTENSIVE 2026</h2>
<p>DAL 29 Giugno al 24 Luglio 2026</p>

<p>S.I.S. PER BAMBINI DAGLI 7 AI 13 ANNI:</p>
<p>I bambini studieranno Danza Classica, Fisiotecnica, Modern, Contemporaneo.</p>
<p>1° SETTIMANA<br>DAL 29 GIUGNO AL 03 LUGLIO<br>Docenti:</p>
<p>MICHELA SARTORELLI<br>– Direttrice Professione Danza Pescara (Classico)</p>
<p>4° SETTIMANA<br>DAL 20 LUGLIO AL 24 LUGLIO<br>Docenti:</p>
<p>SIMONA FERRAZZA<br>Docente Dutch National Ballet Academy (Classico)</p>
<p>Costi:</p>
<p>1° Settimana:<br>Euro 60,00</p>
<p>3° Settimana:<br>Euro 200,00 (con stage)</p>
<p>3° Settimana dal 15 al 18 Luglio:<br>Euro<br>100,00<br>(senza stage)</p>
<p>Costo di quattro settimane:<br>Euro 350,00</p>

<p>S.I.S. PER RAGAZZI E RAGAZZE DAI 14 AI 25:</p>
<p>Gli allievi affronteranno lo studio della Danza Classica, Tecnica delle Punte, Contemporaneo.</p>
<p>1° SETTIMANA<br>DAL 29 GIUGNO AL 03 LUGLIO<br>Docenti:</p>
<p>GIOVANNI LA ROCCA<br>– Contemporary Freelance Teacher (Contemporaneo)</p>
<p>4° SETTIMANA<br>DAL 20 LUGLIO AL 31 LUGLIO<br>Docenti:</p>
<p>ANA PRESTA<br>– International Ballet Master (Contemporaneo, Repertorio Forsythe)</p>
<p>Costi:</p>
<p>1° Settimana:<br>Euro 80,00</p>
<p>Costo di quattro settimane:<br>Euro 500,00</p>

<p>BORSE DI STUDIO:</p>
</body></html>
"""


def _offerings():
    return {o.id.rsplit("-", 1)[1]: o for o in p._build_offerings(_HTML)}


def test_two_tracks_with_ids():
    offs = _offerings()
    assert set(offs) == {"bambini", "ragazzi"}
    assert offs["bambini"].id == "professione-danza-pescara/summer-intensive-2026-bambini"


def test_dates_year_from_header():
    offs = _offerings()
    assert (offs["bambini"].schedule.start, offs["bambini"].schedule.end) == (
        date(2026, 6, 29),
        date(2026, 7, 24),
    )
    # Youth's 4th week stretches the overall span to 31 July.
    assert offs["ragazzi"].schedule.end == date(2026, 7, 31)


def test_ages_per_track():
    offs = _offerings()
    assert offs["bambini"].age_range == {"min": 7, "max": 13}
    assert offs["ragazzi"].age_range == {"min": 14, "max": 25}


def test_genres_curriculum_scoped():
    offs = _offerings()
    assert offs["bambini"].genres == ["classical", "contemporary"]
    # Youth adds pointe ("Tecnica delle Punte"); the faculty "Repertorio Forsythe"
    # bio must NOT leak a repertoire genre — curriculum sentence only.
    assert offs["ragazzi"].genres == ["classical", "pointe", "contemporary"]


def test_prices_split_line_senza_stage():
    bambini = _offerings()["bambini"]
    by_amount = {pr.amount: pr for pr in bambini.prices}
    assert set(by_amount) == {60, 200, 100, 350}
    assert by_amount[100].notes == "senza stage"
    assert by_amount[350].label == "Costo di quattro settimane"
    assert all(pr.type == "tuition" for pr in bambini.prices)


def test_teachers_names_only_incl_dashless_bio():
    bambini = _offerings()["bambini"]
    names = [t.name for t in bambini.teachers]
    # "MICHELA SARTORELLI" (dashed) and "SIMONA FERRAZZA" (dash-less week-4 bio).
    assert names == ["Michela Sartorelli", "Simona Ferrazza"]
    assert all(not t.affiliations for t in bambini.teachers)


def test_raises_without_year():
    with pytest.raises(ValueError):
        p._build_offerings("<html><body><p>In aggiornamento</p></body></html>")
