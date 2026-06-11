"""Offline tests for the Conservatório Annarella scraper.

Inline snippets mirror the real `content.rendered` prose (PT). No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.models import VideoReq
from intensive_dance.scrapers import conservatorio_annarella as ann

SUMMER = """
CURSO INTENSIVO DE VERÃO INFORMAÇÕES
SEMANAS: 29 junho - 3 julho 20 - 24 julho 6 - 10 julho 27 - 31 julho 13 - 17 julho
1ª Gala – 17 de julho 2ª Gala - 31 de Julho * Valores sob consulta
O Curso de Verão 2026, além da habitual excelência ...
O nosso curso está aberto desde os 8 anos até aos 20 anos* *Idade à data do Curso.
As modalidades disponíveis são: Ballet, Contemporâneo, Dança de Carácter,
Preparação Física, Repertório, Técnica de Pas de Deux, Jazz, Técnica de Pontas,
entre outras.
Informamos que o alojamento, alimentação e transportes são da responsabilidade
dos bailarinos e não estão incluídos no valor do curso.
PASSOS PARA INSCRIÇÃO NO CURSO DE VERÃO 2026:
1. Preencher o formulário de inscrição (ao lado).
Requisitos para o vídeo: 1st arabesque a terre and en l'air A pirouette combination
A Petite allegro combination NÃO SÃO ACEITES EXERCÍCIOS NA BARRA PARA MAIORES DE 13 ANOS.
O vídeo deve ser colocado no Youtube como "Não Listado".
NOTA: os alunos com idade inferior a 11 anos e aqueles que já participaram no nosso
Curso em anos anteriores, não têm que enviar vídeo para inscrição.
Data limite para submissão de inscrição: 15 de maio de 2026.
"""

# Edge: single-week winter edition, open-ended age ("maiores de 8 anos"), and a
# curriculum that adds non-genre modalities (Danças Latinas) we must NOT emit.
WINTER = """
CURSO INTENSIVO DE INVERNO INFORMAÇÕES SEMANA: 6 - 11 de janeiro de 2025
Já estão abertas as inscrições* para o Curso de Inverno 2025 ... *Valores sob consulta
O Curso de Inverno destina-se a estudantes maiores de 8 anos.
O programa inclui as variadas modalidades: Ballet, Contemporâneo, Dança de Carácter,
Danças Latinas Preparação Física, Repertório, Técnica de Pas de Deux**, Técnica de Pontas**,
entre outras.
PASSOS PARA INSCRIÇÃO NO CURSO DE INVERNO 2025:
Requisitos para o vídeo: 1st arabesque a terre and en l'air NÃO SÃO ACEITES EXERCÍCIOS NA BARRA
O vídeo deve ser colocado no Youtube como "Não Listado".
NOTA: os alunos com idade igual ou inferior a 12 anos não têm que enviar vídeo.
Data limite para submissão de inscrição: 30 de dezembro de 2024.
"""


def test_summer_dates_and_sessions():
    o = ann._build_summer(SUMMER)
    assert o.id == "conservatorio-annarella/curso-intensivo-de-verao-2026"
    assert o.title == "Curso Intensivo de Verão 2026"
    assert o.schedule.start == date(2026, 6, 29)
    assert o.schedule.end == date(2026, 7, 31)
    # five selectable weeks, each a Session; the cross-month first week is parsed
    # and the month-implied weeks ("20 - 24 julho") inherit the trailing month.
    assert len(o.schedule.sessions) == 5
    assert o.schedule.sessions[0].start == date(2026, 6, 29)
    assert o.schedule.sessions[1].start == date(2026, 7, 20)
    assert "1ª" not in (o.schedule.notes or "")


def test_summer_age_genres_requirements():
    o = ann._build_summer(SUMMER)
    assert o.age_range == {"min": 8, "max": 20}
    # Jazz / Pas de Deux / Preparação Física are not genres in our enum.
    assert o.genres == ["classical", "contemporary", "character", "repertoire", "pointe"]
    assert o.prices == []
    assert o.application.deadline == date(2026, 5, 15)
    assert len(o.application.requirements) == 1
    req = o.application.requirements[0]
    assert isinstance(req, VideoReq)
    assert req.specificity == "specific"
    assert "arabesque" in (req.description or "")
    assert "inferior a 11 anos" in (o.application.notes or "")


def test_winter_single_week_open_age():
    o = ann._build_winter(WINTER)
    assert o.id == "conservatorio-annarella/curso-intensivo-de-inverno-2025"
    assert o.schedule.start == date(2025, 1, 6)
    assert o.schedule.end == date(2025, 1, 11)
    assert o.schedule.sessions == []
    assert o.age_range == {"min": 8, "max": None}
    assert o.genres == ["classical", "contemporary", "character", "repertoire", "pointe"]
    assert o.application.deadline == date(2024, 12, 30)


def test_winter_falls_back_when_no_date():
    o = ann._build_winter("Curso de Inverno 2027 — datas por definir. maiores de 8 anos")
    assert o.schedule.start is None
    assert o.schedule.end is None
    assert o.id.endswith("inverno-2027")
