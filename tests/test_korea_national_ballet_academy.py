"""Unit tests for the Korea National Ballet Academy scraper (Korean CMS page).

These pin the structural table parse (label cell → date-span cell, skipping the
quarterly 분기 rows) and the Korean date-span regex: a same-year summer span and a
cross-year winter span whose end states its own year. Inline KR-shaped strings,
no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import korea_national_ballet_academy as knb

# The vacation-timetable popup table, shaped like the live markup: a header row,
# quarterly (분기) rows we must skip, and the two 방학 (vacation) rows we keep — the
# summer end omits its year, the winter end (crossing into 2027) states it.
_TABLE_HTML = """
<table>
  <tr><td>월</td><td>수강료 납부기간</td><td>수강기간</td></tr>
  <tr><td>1분기</td><td>2025년 12월 9일(화) ~ 2025년 12월 24일(수)</td>
      <td>1분기 1월 13일(화) ~ 3월 31일(화)</td></tr>
  <tr><td>3분기</td><td>2026년 6월 2일(화) ~ 6월 23일(화)</td>
      <td>3분기 7월 1일(수) ~ 9월 30일(수)</td></tr>
  <tr><td>여름방학</td><td>2026년 7월 27일(월) ~ 8월 3일(월) (1주)</td><td></td></tr>
  <tr><td>겨울방학</td><td>2026년 12월 14일(월) ~ 2027년 1월 10일(일) (4주)</td><td></td></tr>
</table>
"""


def test_period_rows_keeps_only_vacation_rows():
    rows = knb._period_rows(_TABLE_HTML)
    assert set(rows) == {"여름방학", "겨울방학"}
    assert rows["여름방학"] == "2026년 7월 27일(월) ~ 8월 3일(월) (1주)"


def test_date_span_same_year_inherits_start_year():
    start, end = knb._date_span("2026년 7월 27일(월) ~ 8월 3일(월) (1주)")
    assert start == date(2026, 7, 27)
    assert end == date(2026, 8, 3)


def test_date_span_cross_year_uses_end_year():
    start, end = knb._date_span("2026년 12월 14일(월) ~ 2027년 1월 10일(일) (4주)")
    assert start == date(2026, 12, 14)
    assert end == date(2027, 1, 10)


def test_date_span_no_match():
    assert knb._date_span("선착순 모집") == (None, None)


def test_build_offerings_two_editions():
    offerings = knb._build_offerings(_TABLE_HTML)
    assert len(offerings) == 2

    summer = next(o for o in offerings if o.id.endswith("summer-intensive-2026"))
    assert summer.schedule.start == date(2026, 7, 27)
    assert summer.schedule.end == date(2026, 8, 3)
    assert summer.schedule.season == "2026"
    assert summer.genres == ["classical"]
    assert summer.organization.slug == "korea-national-ballet-academy"
    assert summer.location is not None
    assert summer.location.country == "KR"
    assert summer.location.city == "Seoul"
    # The raw Korean span is kept verbatim in the schedule note (incl. the 주 count).
    assert summer.schedule.notes is not None
    assert "(1주)" in summer.schedule.notes
    # First-come registration note is preserved; no fabricated fee/age.
    assert summer.application.notes is not None
    assert "선착순" in summer.application.notes
    assert summer.prices == []
    assert summer.age_range is None

    winter = next(o for o in offerings if o.id.endswith("winter-intensive-2026"))
    # The winter edition's season anchors on its start year, not the 2027 end.
    assert winter.schedule.season == "2026"
    assert winter.schedule.start == date(2026, 12, 14)
    assert winter.schedule.end == date(2027, 1, 10)


def test_build_offerings_empty_when_no_vacation_rows():
    html = "<table><tr><td>1분기</td><td>2026년 6월 2일(화) ~ 6월 23일(화)</td></tr></table>"
    assert knb._build_offerings(html) == []
