"""Unit tests for the PNSD Rosella Hightower scraper (server-rendered /stages).

These pin the French-source parsing of the summer "stages" hub: segmenting the
"STAGES - ETE" block into per-edition stages, the date range (incl. the
month-omitted start in STAGE 2), the open-ended age, curriculum genres (jazz out
of scope), and the per-edition faculty split by discipline (jazz names dropped).
A spring "dates à venir" block must yield nothing. Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import pnsd_rosella_hightower as p

# Mirrors the real page: the intro/curriculum line, the summer block with four
# dated editions (STAGE 2 omits the month on its start day), faculty split by
# discipline (incl. a JAZZ row we must drop), then a spring block with no dates.
_HTML = """
<html><body>
<h3>Le Pôle National Supérieur de Danse Rosella Hightower propose, au printemps
et en été, des stages divers.</h3>
<p>Possibilité d'hébergement sur place et pension complète.
Classique/Contemporain/Jazz Pointes Technique garçon Workshops
Répertoire classique et contemporain Pilates/Réveil corporel
Stages à partir de 10 ans</p>
<p class="h3">STAGES - ETE 2026</p>
<b>STAGE 1 : du Samedi 27 Juin au Jeudi 2 Juillet 2026</b>
<p>Professeur.e.s : Reveil corporel avec Studio Pilates Cannes
CLASSIQUE : Dominique Lainé, Mikhail Soloviev
CONTEMPORAIN : Céline Galli, Jeanne Chossat
JAZZ : Cécile Lorenzelli</p>
<a>Planning</a>
<b>STAGE 2 : du Mercredi 8 au Mardi 14 Juillet 2026</b>
<p>Portes ouvertes le dernier jour du stage
Professeur.e.s : Reveil corporel avec Studio Pilates Cannes
CLASSIQUE : Hélène Bouchet, Siner Gonenc
CONTEMPORAIN : Valeria Vellei
JAZZ : Marguerite Boffa, Jeffrey Carter</p>
<a>Planning</a>
<b>STAGE 3 : du Vendredi 17 au Jeudi 23 Juillet 2026</b>
<p>Portes ouvertes le dernier jour du stage
Professeur.e.s : Reveil corporel avec Studio Pilates Cannes
CLASSIQUE : Karine Seneca, Carlotta Pini
CONTEMPORAIN : Harris Gkekas
JAZZ : Valène Azy Roux, Jeffrey Carter</p>
<a>Planning</a>
<b>STAGE 4 : du Jeudi 20 au Mercredi 26 Août 2026</b>
<p>Portes ouvertes le dernier jour du stage
Professeur.e.s : Reveil corporel avec Studio Pilates Cannes
CLASSIQUE : Karine Seneca, Dominique Lainé
CONTEMPORAIN : David Russo, Didy Veldman
JAZZ : Valène Azy Roux, Karine Plantadit</p>
<a>Planning</a>
<a>Formulaire d'inscription</a>
<a>Planning type</a>
<p class="h3">STAGES - PRINTEMPS 2027</p>
<b>STAGE 1 : dates à venir</b>
<p>Professeur.e.s : Reveil corporel CLASSIQUE CONTEMPORAIN</p>
<a>Formulaire d'inscription</a>
</body></html>
"""


def test_build_offerings_one_per_summer_edition():
    offerings = p._build_offerings(_HTML)
    # Four dated summer editions; the spring "dates à venir" block yields nothing.
    assert [o.id for o in offerings] == [
        "pnsd-rosella-hightower/stage-ete-2026-1",
        "pnsd-rosella-hightower/stage-ete-2026-2",
        "pnsd-rosella-hightower/stage-ete-2026-3",
        "pnsd-rosella-hightower/stage-ete-2026-4",
    ]
    assert [o.title for o in offerings] == [
        "Stage d'été 2026 — Stage 1",
        "Stage d'été 2026 — Stage 2",
        "Stage d'été 2026 — Stage 3",
        "Stage d'été 2026 — Stage 4",
    ]


def test_dates_full_range():
    assert p._date_range("du Samedi 27 Juin au Jeudi 2 Juillet 2026") == (
        date(2026, 6, 27),
        date(2026, 7, 2),
    )


def test_dates_month_omitted_on_start_inherits_end_month():
    # STAGE 2: "du Mercredi 8 au Mardi 14 Juillet 2026" — start has no month.
    assert p._date_range("du Mercredi 8 au Mardi 14 Juillet 2026") == (
        date(2026, 7, 8),
        date(2026, 7, 14),
    )


def test_dates_cross_month_august():
    assert p._date_range("du Jeudi 20 au Mercredi 26 Août 2026") == (
        date(2026, 8, 20),
        date(2026, 8, 26),
    )


def test_dates_absent():
    assert p._date_range("dates à venir") == (None, None)


def test_age_open_ended():
    assert p._age_range("Stages à partir de 10 ans") == {"min": 10}
    assert p._age_range("aucune mention d'âge") is None


def test_genres_curriculum_classical_and_contemporary_no_jazz():
    genres = p._genres(
        "CLASSIQUE : x CONTEMPORAIN : y JAZZ : z Pointes Répertoire classique et contemporain"
    )
    assert "classical" in genres
    assert "contemporary" in genres
    assert "pointe" in genres
    assert "repertoire" in genres
    # Jazz has no enum value; it never leaks a genre.
    assert all(g in {"classical", "contemporary", "pointe", "repertoire"} for g in genres)


def test_teachers_split_by_discipline_drop_jazz():
    body = (
        "Professeur.e.s : Reveil corporel CLASSIQUE : Dominique Lainé, Mikhail Soloviev "
        "CONTEMPORAIN : Céline Galli, Jeanne Chossat JAZZ : Cécile Lorenzelli Planning"
    )
    teachers = p._teachers(body)
    assert [(t.name, t.role) for t in teachers] == [
        ("Dominique Lainé", "Classique"),
        ("Mikhail Soloviev", "Classique"),
        ("Céline Galli", "Contemporain"),
        ("Jeanne Chossat", "Contemporain"),
    ]
    # The jazz-only teacher is dropped.
    assert all(t.name != "Cécile Lorenzelli" for t in teachers)


def test_open_house_note_does_not_leak_faculty():
    offerings = p._build_offerings(_HTML)
    stage2 = offerings[1]
    assert stage2.schedule.notes == "Portes ouvertes le dernier jour du stage"
    # Stage 1 has no open-house line on the page → no note.
    assert offerings[0].schedule.notes is None


def test_no_summer_block_yields_nothing():
    assert p._build_offerings("<html><body><p>Pas de stages annoncés.</p></body></html>") == []
