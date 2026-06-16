"""Tests for the Escola do Teatro Bolshoi no Brasil scraper.

Offline — no network. Inline HTML snippets mirror the live source's structure
(the `audicao-inscricao-meta` label/value block and the `curso-descr-content`
description) as captured on 2026-06-08. The course text is Portuguese, as the
real site serves it.
"""

from __future__ import annotations

from datetime import date

from selectolax.parser import HTMLParser

from intensive_dance.scrapers.escola_bolshoi_brasil import (
    _age_range,
    _build_offering,
    _course_paths,
    _date_range,
    _gender,
    _genres,
    _levels,
    _location,
    _prices,
    _teacher_name,
)


# --- a complete Joinville course page (Inverno cohort, sold out) ---------------

PAGE_CLASSICAL = """
<html><body>
  <h1>Ballet Clássico Bolshoi Brasil - Intermediário/Avançado (F/M)</h1>
  <div class="curso-descr-content">
    <p><b>Ballet Clássico Bolshoi Brasil - Intermediário/Avançado (F/M)</b><br>
    <b>Professor: </b>Denys Nevidomyy<br>
    <b>Horário:</b> 14h às 16h<br></p>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Valor da inscrição</span>
    <span class="audicao-inscricao-meta__val">R$ 445,00</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Período do curso</span>
    <span class="audicao-inscricao-meta__val">21/07/2026 a 24/07/2026</span>
  </div>
  <div class="audicao-inscricao-meta audicao-inscricao-meta--full">
    <span class="audicao-inscricao-meta__label"><i></i> Local</span>
    <span class="audicao-inscricao-meta__val">Escola do Teatro Bolshoi no Brasil</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Cidade / UF</span>
    <span class="audicao-inscricao-meta__val">Joinville / SC</span>
  </div>
  <div class="audicao-inscricao-meta audicao-inscricao-meta--full">
    <span class="audicao-inscricao-meta__label"><i></i> Professores</span>
    <span class="audicao-inscricao-meta__val">Denys Nevidomyy</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Idade</span>
    <span class="audicao-inscricao-meta__val">14–100</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Sexo</span>
    <span class="audicao-inscricao-meta__val">Ambos os sexos</span>
  </div>
  <p>Não há mais vagas para este curso.</p>
</body></html>
"""

# A free pop-up workshop in a different city, no Professores meta; teacher comes
# from neither (the description names no professor here).
PAGE_BELEM_FREE = """
<html><body>
  <h1>Workshop Ballet Clássico Iniciante</h1>
  <div class="curso-descr-content">
    <p>Workshop Ballet Clássico Iniciante<br>Data: 02/09/2026<br>
    Local: Theatro da Paz<br>Pré-Requisitos: nível básico.</p>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Valor da inscrição</span>
    <span class="audicao-inscricao-meta__val">R$ 0,00</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Período do curso</span>
    <span class="audicao-inscricao-meta__val">02/09/2026 a 02/09/2026</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Cidade / UF</span>
    <span class="audicao-inscricao-meta__val">Belém / PA</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Idade</span>
    <span class="audicao-inscricao-meta__val">9–12</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Sexo</span>
    <span class="audicao-inscricao-meta__val">Ambos os sexos</span>
  </div>
</body></html>
"""

# Gala course where the Professores meta is blank → teacher from the description.
PAGE_GALA_DESC_TEACHER = """
<html><body>
  <h1>Ensaios Gala Bolshoi Brasil - Intermediário / Avançado (F/M)</h1>
  <div class="curso-descr-content">
    <p><b>Ensaio Gala Bolshoi Brasil - Intermediário / Avançado (F/M)<br></b>
    <b>Professor: Maikon Golini<br></b><b>Horário:</b> 16h às 18h<br>
    <b>Faixa Etária:</b> a partir de 14 anos<br></p>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Período do curso</span>
    <span class="audicao-inscricao-meta__val">21/07/2026 a 25/07/2026</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Cidade / UF</span>
    <span class="audicao-inscricao-meta__val">Joinville / SC</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Idade</span>
    <span class="audicao-inscricao-meta__val">14–100</span>
  </div>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Sexo</span>
    <span class="audicao-inscricao-meta__val">Ambos os sexos</span>
  </div>
</body></html>
"""

# A teacher-training course → out of student scope → skipped.
PAGE_TEACHER_TRAINING = """
<html><body>
  <h1>Método Vaganova Bolshoi Brasil – Módulo II: 4º e 5º ano - Curso para Professores (F/M)</h1>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Período do curso</span>
    <span class="audicao-inscricao-meta__val">21/07/2026 a 25/07/2026</span>
  </div>
</body></html>
"""


# --- pure helpers --------------------------------------------------------------


def test_date_range() -> None:
    assert _date_range("21/07/2026 a 24/07/2026") == (date(2026, 7, 21), date(2026, 7, 24))
    assert _date_range("20/07/2026 a 20/07/2026") == (date(2026, 7, 20), date(2026, 7, 20))
    assert _date_range(None) == (None, None)
    assert _date_range("sem data") == (None, None)


def test_age_range_bounded_and_open_sentinel() -> None:
    assert _age_range("11–14") == {"min": 11, "max": 14}
    assert _age_range("17–25") == {"min": 17, "max": 25}
    # 100 is the booking-form "open" sentinel → null upper bound.
    assert _age_range("14–100") == {"min": 14, "max": None}
    assert _age_range(None) is None


def test_gender() -> None:
    assert _gender("Feminino") == "female"
    assert _gender("Masculino") == "male"
    assert _gender("Ambos os sexos") == "both"
    assert _gender(None) == "both"


def test_genres() -> None:
    assert _genres("Ballet Clássico Bolshoi Brasil - Adulto Iniciante (F/M)") == ["classical"]
    assert _genres("Dança Contemporânea Bolshoi Brasil") == ["contemporary"]
    # Repertory variations are danced on the classical syllabus → classical added.
    assert _genres("Variações de Repertório Bolshoi Brasil – Adulto (F)") == [
        "classical",
        "repertoire",
    ]
    assert _genres("Ensaios Gala Bolshoi Brasil") == ["classical", "repertoire"]


def test_levels() -> None:
    assert _levels("Ballet Clássico - Intermediário/Avançado (F/M)") == [
        "intermediate",
        "advanced",
    ]
    assert _levels("Ballet Clássico - Adulto Iniciante (F/M)") == ["beginner", "open"]
    assert _levels("Workshop de Preparação Física para Bailarinos") == []


def test_prices_and_free_workshop() -> None:
    prices = _prices(HTMLParser(PAGE_CLASSICAL))
    assert len(prices) == 1
    assert prices[0].amount == 445.0
    assert prices[0].currency == "BRL"
    # R$ 0,00 → no Price emitted.
    assert _prices(HTMLParser(PAGE_BELEM_FREE)) == []


def test_location_per_course() -> None:
    joinville = _location(HTMLParser(PAGE_CLASSICAL))
    assert joinville.city == "Joinville"
    assert joinville.country == "BR"
    assert joinville.venue == "Escola do Teatro Bolshoi no Brasil"
    belem = _location(HTMLParser(PAGE_BELEM_FREE))
    assert belem.city == "Belém"


def test_teacher_from_meta_and_description() -> None:
    assert _teacher_name(HTMLParser(PAGE_CLASSICAL)) == "Denys Nevidomyy"
    # Meta blank → name parsed from the "Professor: …<br>" description line,
    # not glued to the following "Horário" field.
    assert _teacher_name(HTMLParser(PAGE_GALA_DESC_TEACHER)) == "Maikon Golini"
    # Belém workshop names no professor anywhere.
    assert _teacher_name(HTMLParser(PAGE_BELEM_FREE)) is None


# --- discovery -----------------------------------------------------------------


def test_course_paths_dedupe_across_pages() -> None:
    page_a = '<a href="/curso/780/ballet-classico"></a><a href="/curso/778/danca"></a>'
    # Second tab echoes 780 and adds 758.
    page_b = '<a href="/curso/780/ballet-classico"></a><a href="/curso/758/vivencia"></a>'
    paths = _course_paths([page_a, page_b])
    # Sorted by numeric id, deduped.
    assert paths == [
        "/curso/758/vivencia",
        "/curso/778/danca",
        "/curso/780/ballet-classico",
    ]


# --- end-to-end offering -------------------------------------------------------


def test_build_offering_classical_sold_out() -> None:
    o = _build_offering(PAGE_CLASSICAL, "https://escolabolshoi.com.br/curso/780/ballet-classico")
    assert o is not None
    assert o.id == "escola-bolshoi-brasil/ballet-classico"
    assert o.title == "Ballet Clássico Bolshoi Brasil - Intermediário/Avançado (F/M)"
    assert o.genres == ["classical"]
    assert o.level == ["intermediate", "advanced"]
    assert o.age_range == {"min": 14, "max": None}
    assert o.organization.country == "BR"
    assert o.location is not None
    assert o.location.city == "Joinville"
    assert o.schedule.start == date(2026, 7, 21)
    assert o.schedule.end == date(2026, 7, 24)
    assert o.schedule.timezone == "America/Sao_Paulo"
    assert len(o.schedule.sessions) == 1
    assert o.schedule.sessions[0].gender == "both"
    assert [t.name for t in o.teachers] == ["Denys Nevidomyy"]
    assert len(o.prices) == 1 and o.prices[0].currency == "BRL"
    # Sold out → application closed; open-enrollment course → no audition.
    assert o.application.status == "closed"
    assert [r.type for r in o.application.requirements] == ["none"]


def test_build_offering_belem_free_open() -> None:
    o = _build_offering(
        PAGE_BELEM_FREE, "https://escolabolshoi.com.br/curso/816/workshop-ballet-classico-iniciante"
    )
    assert o is not None
    assert o.location is not None
    assert o.location.city == "Belém"
    assert o.age_range == {"min": 9, "max": 12}
    assert o.prices == []
    assert o.application.status == "open"
    assert o.teachers == []


def test_teacher_training_course_skipped() -> None:
    o = _build_offering(
        PAGE_TEACHER_TRAINING, "https://escolabolshoi.com.br/curso/798/metodo-vaganova"
    )
    assert o is None


# A physical-conditioning workshop teaches no dance genre → out of scope.
PAGE_PHYSICAL_PREP = """
<html><body>
  <h1>Workshop de Preparação Física para Bailarinos</h1>
  <div class="audicao-inscricao-meta">
    <span class="audicao-inscricao-meta__label"><i></i> Período do curso</span>
    <span class="audicao-inscricao-meta__val">20/07/2026 a 20/07/2026</span>
  </div>
</body></html>
"""


def test_physical_prep_workshop_skipped() -> None:
    # Not a dance class — must not be emitted with a default "classical" genre.
    o = _build_offering(
        PAGE_PHYSICAL_PREP, "https://escolabolshoi.com.br/curso/999/workshop-preparacao-fisica"
    )
    assert o is None
