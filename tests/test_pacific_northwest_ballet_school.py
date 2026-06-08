"""Unit tests for the Pacific Northwest Ballet School Summer Intensive scraper.

PNB is an API scrape of two WordPress pages whose `content.rendered` bodies are
populated (unlike the SAB/ABT/Boston Elementor trap) but interleaved with
Elementor `<style>` blocks: the "summer-intensive" detail page (ages, curriculum
→ genres, level-based tuition, audition policy) and the "summer" hub (the one
line of dated schedule). These fragments pin the judgement calls a hash check
can't catch: stripping the Elementor CSS, anchoring the date range on the
Intensive heading (not the Day Program's identical span earlier on the hub), the
two level-band tuition lines, the curriculum-only genre match, and the
audition→video requirement. No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance import parse
from intensive_dance.models import VideoReq
from intensive_dance.scrapers import pacific_northwest_ballet_school as pnb

# Detail page (`content.rendered`): ages, the curriculum list (the genre source,
# incl. out-of-scope Hip Hop / Jazz / Pas de Deux), the two level-band tuition
# lines, and the audition policy. An Elementor <style> block must be stripped.
_DETAIL = """
<div class="elementor">
  <style>.elementor-element-abc{--display:flex;color:$bogus}</style>
  <h1>PNB Summer Intensive</h1>
  <p>PNB School&#8217;s Summer Intensive offers dance students ages 12 &#8211;19
  the highest caliber of intensive classical ballet training.</p>
  <p>PNB School&#8217;s Summer Intensive curriculum includes a variety of dance
  forms, including Technique, Pointe, Variations, Pas de Deux, Modern, Hip Hop,
  Jazz, Character, Strength Training, and more.</p>
  <p>Does PNB School&#8217;s Summer Intensive require an audition? Yes, PNB School
  requires an audition for Summer Intensive.</p>
  <p>What is the tuition cost for PNB School&#8217;s Summer Intensive? Tuition for
  Levels IV &amp; V costs a total of $2,680. Tuition for Levels VI, VII, VIII, and
  Advanced C costs $2,990.</p>
</div>
"""

# Hub page (`content.rendered`): several summer programs each with a "Schedule …"
# line. The Summer Day Program (out of scope) carries the SAME span and sits
# BEFORE the Intensive block — so the date anchor must key off the Intensive
# heading. The admission sentence ("advanced ballet students") also lives here.
_HUB = """
<div>
  <h3>Summer Day Program at the Francia Russell Center (Ages 8 - 14)</h3>
  <p>A great introduction to PNB School for intermediate dancers.</p>
  <p>Schedule July 6 &#8211; August 7, 2026 Tuition Varies by level</p>
  <h3>PNB School Summer Intensive (Ages 12 &#8211; 19)</h3>
  <p>Summer Intensive offers advanced ballet students ages 12-19 the highest
  caliber of intensive classical training.</p>
  <p>Schedule July 6 &#8211; August 7, 2026 Tuition Varies by level Location
  Phelps Center // 301 Mercer Street // Seattle, WA 98109</p>
</div>
"""


def _text(html: str) -> str:
    return pnb._render_text(html)


# --- dates --------------------------------------------------------------------


def test_dates_anchored_on_intensive_heading():
    # Both the Day Program and the Intensive list "July 6 – August 7, 2026"; the
    # anchor must take the Intensive block, not the earlier Day Program one.
    assert pnb._dates(_text(_HUB)) == (date(2026, 7, 6), date(2026, 8, 7))


def test_dates_none_when_absent():
    assert pnb._dates("<div>no schedule here</div>") == (None, None)


# --- ages / levels ------------------------------------------------------------


def test_age_range_en_dash_with_stray_space():
    assert parse.extract_age_range(_text(_DETAIL), pnb._AGE) == {"min": 12, "max": 19}


def test_levels_advanced_from_admission_sentence():
    assert pnb._levels(_text(_HUB)) == ["advanced"]


def test_levels_empty_when_not_stated():
    assert pnb._levels("a summer program for young dancers") == []


# --- genres -------------------------------------------------------------------


def test_genres_from_curriculum_list_only():
    # Technique→classical, Pointe, Variations→repertoire, Modern→contemporary,
    # Character. Hip Hop / Jazz / Pas de Deux aren't register genres → dropped.
    assert pnb._genres(_text(_DETAIL)) == [
        "classical",
        "pointe",
        "repertoire",
        "contemporary",
        "character",
    ]


def test_genres_classical_only_when_silent():
    assert pnb._genres("an intensive classical ballet program") == ["classical"]


# --- prices -------------------------------------------------------------------


def test_prices_two_level_bands_tuition_only():
    prices = pnb._prices(_text(_DETAIL))
    assert [(p.label, p.amount, p.currency, p.includes) for p in prices] == [
        ("Tuition (Levels IV & V)", 2680.0, "USD", ["tuition"]),
        ("Tuition (Levels VI–VIII & Advanced C)", 2990.0, "USD", ["tuition"]),
    ]


# --- requirements -------------------------------------------------------------


def test_requirements_audition_to_video():
    reqs = pnb._requirements(_text(_DETAIL))
    assert len(reqs) == 1
    assert isinstance(reqs[0], VideoReq)
    assert reqs[0].specificity == "unspecific"


def test_requirements_empty_when_no_audition_stated():
    assert pnb._requirements("a holistic summer program") == []


# --- end-to-end ---------------------------------------------------------------


def test_build_offerings_single_dated_edition():
    offerings = pnb._build_offerings(_text(_DETAIL), _text(_HUB), date(2026, 1, 1))
    assert len(offerings) == 1
    o = offerings[0]
    assert o.id == "pacific-northwest-ballet-school/summer-intensive-2026"
    assert o.title == "Summer Intensive"
    assert o.genres == ["classical", "pointe", "repertoire", "contemporary", "character"]
    assert o.level == ["advanced"]
    assert o.age_range == {"min": 12, "max": 19}
    assert o.schedule.season == "2026"
    assert o.schedule.start == date(2026, 7, 6)
    assert o.schedule.end == date(2026, 8, 7)
    assert o.schedule.timezone == "America/Los_Angeles"
    assert o.location is not None
    assert (o.location.venue, o.location.city, o.location.country) == (
        "The Phelps Center",
        "Seattle",
        "US",
    )
    assert [p.amount for p in o.prices] == [2680.0, 2990.0]
    assert o.application.status is None
    assert o.application.deadline is None
    assert isinstance(o.application.requirements[0], VideoReq)


def test_no_offering_when_dates_absent():
    offerings = pnb._build_offerings(_text(_DETAIL), "<div>no dates</div>", date(2026, 1, 1))
    assert offerings == []
