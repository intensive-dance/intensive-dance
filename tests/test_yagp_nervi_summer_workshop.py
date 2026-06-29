"""Offline tests for the YGP Nervi summer-workshop scraper.

Inline WP page dicts + inline guide text (the PDF is read elsewhere). No network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import yagp_nervi_summer_workshop as y

CONTENT_2025 = """
<p>This special one-week program gives participants a taste of life in a
professional dance company, with master classes in classical technique,
contemporary works and a casting/repertoire process.</p>
<p>APPLICATION DEADLINE - FEBRUARY 15, 2025</p>
<a href="https://yagp.org/misc/Downloads/2025/YGP%202025%20NERVI%20FESTIVAL,%20ITALY,%20GUIDE.pdf">GUIDE</a>
<a href="https://docs.google.com/forms/apply">APPLICATION</a>
"""

GUIDE_2025 = """
Registration will be held on Sunday, July 20 with the time and location TBA.
Please note that every dancer will be performing in both Gala performances on
July 26 and July 27, featuring the Grand Defile.
A private lesson is available; the fee is €100 per lesson. Tutus €150.
"""


def _page(slug, title, content):
    return {
        "slug": slug,
        "link": f"https://yagp.org/{slug}/",
        "title": {"rendered": title},
        "content": {"rendered": content},
    }


PAGES = [
    _page(
        "the-ygp-2024-international-summer-workshop-at-nervi-festival",
        "The YGP 2024 International Summer Workshop at Nervi Festival",
        "<p>old</p>",
    ),
    _page(
        "the-ygp-2025-international-summer-workshop-at-nervi-festival",
        "The YGP 2025 International Summer Workshop at Nervi Festival",
        CONTENT_2025,
    ),
    # the stray duplicate must be ignored even though it has the highest-looking title
    _page(
        "yagp-2025-tampa-fl-finals",
        "The YGP 2025 International Summer Workshop at Nervi Festival Copy",
        "<p>copy</p>",
    ),
    _page("yagp-2002-new-york-city-finals", "YAGP 2002 - NEW YORK CITY FINALS", "<p>comp</p>"),
]


def test_select_latest_skips_copy_and_non_nervi():
    page = y._select_latest(PAGES)
    assert page is not None
    assert page["slug"] == "the-ygp-2025-international-summer-workshop-at-nervi-festival"


def test_guide_url_extracted_from_content():
    url = y._guide_url(CONTENT_2025)
    assert url is not None
    assert url.endswith("GUIDE.pdf")


def test_build_offering_core():
    page = y._select_latest(PAGES)
    assert page is not None
    o = y._build_offering(page, GUIDE_2025)
    assert o.id == "yagp-nervi-summer-workshop/nervi-2025"
    assert o.title == "YGP 2025 International Summer Workshop at Nervi Festival"
    assert o.schedule.season == "2025"
    # start = registration day, end = last gala (kept though ended, IDR-24)
    assert o.schedule.start == date(2025, 7, 20)
    assert o.schedule.end == date(2025, 7, 27)
    assert "Gala performances" in (o.schedule.notes or "")
    assert o.genres == ["classical", "contemporary", "repertoire"]
    assert o.location is not None
    assert o.location.city == "Genoa"


def test_faithful_nulls_and_deadline():
    page = y._select_latest(PAGES)
    assert page is not None
    o = y._build_offering(page, GUIDE_2025)
    # ages + tuition not stated → not invented; the €100/€150 extras are NOT prices
    assert o.age_range is None
    assert o.prices == []
    assert o.application.deadline == date(2025, 2, 15)
    assert o.application.url is not None
    assert o.application.url.endswith("at-nervi-festival/")


def test_missing_guide_leaves_dates_null():
    page = y._select_latest(PAGES)
    assert page is not None
    o = y._build_offering(page, "")
    assert o.schedule.start is None
    assert o.schedule.end is None
    assert o.schedule.season == "2025"  # still known from the title


def test_no_nervi_page_selects_none():
    assert y._select_latest([_page("about-us", "About", "<p>x</p>")]) is None
