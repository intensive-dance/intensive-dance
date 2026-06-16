"""Unit tests for the MOSA Ballet School scraper (sitemap + Odoo event pages).

These pin the discovery filter (which sitemap events are real training offerings)
and the Odoo-page parsing: ISO dates from `<time data-oe-expression>`, prices from
schema.org `Offer` microdata (with the "Lunch Included" -> meals mapping), the
open/closed registration status, and ages (clean title vs noisy body). Inline
HTML, no network.
"""

from __future__ import annotations

from datetime import date

from selectolax.parser import HTMLParser

from intensive_dance.scrapers import mosa_ballet_school as mosa


# --- discovery filter ---------------------------------------------------------


def test_in_scope_keeps_training_events():
    assert mosa._in_scope("august-signature-intensive-course-2026-age-12-29-231")
    assert mosa._in_scope("exploring-ballet-other-dances-age-8-12-august-2026-232")
    assert mosa._in_scope("july-mosa-intensive-2026-230")


def test_charleston_masterclass_is_out_of_scope():
    # The Charleston is a 1920s social dance event — not a ballet training offering.
    assert not mosa._in_scope("masterclass-charleston-222")


def test_in_scope_drops_non_training_events():
    for slug in [
        "online-auditions-for-2026-2027-213",
        "annual-gala-2023-at-15-00-85",
        "annual-recital-2026-friday-3-july-at-7pm-251",
        "workshop-dance-and-parkinson-s-disease-82",
        "admission-test-mosa-preparation-program-9-12-12-june-2026-250",
        "open-doors-april-2026-by-registration-only-245",
        # Professional-development courses FOR pianists/teachers, not student
        # intensives — they pass _KEEP on "intensive" but are out of scope.
        "ballet-pianists-summer-intensive-2024-from-18-yo-111",
        "ballet-teachers-summer-intensive-2024-from-18-yo-112",
    ]:
        assert not mosa._in_scope(slug), slug


def test_parse_event_urls_from_raw_and_rendered_sitemap():
    # The proxy 403s /sitemap.xml and renders it inside Chromium's XML-viewer
    # wrapper; the /event/ URLs survive verbatim in both forms, so discovery must
    # extract the same in-scope set whether it sees raw XML or the wrapper.
    raw_xml = (
        '<?xml version="1.0"?><urlset>'
        "<url><loc>https://www.mosaballetschool.eu/event/july-mosa-intensive-2026-230</loc></url>"
        "<url><loc>https://www.mosaballetschool.eu/event/annual-gala-2023-85</loc></url>"
        "<url><loc>https://www.mosaballetschool.eu/about-us</loc></url>"
        "</urlset>"
    )
    rendered = (
        "<html><body><div class='line'><span>&lt;loc&gt;"
        "https://www.mosaballetschool.eu/event/july-mosa-intensive-2026-230"
        "&lt;/loc&gt;</span></div><div class='line'><span>&lt;loc&gt;"
        "https://www.mosaballetschool.eu/event/annual-gala-2023-85"
        "&lt;/loc&gt;</span></div></body></html>"
    )
    expected = ["https://www.mosaballetschool.eu/event/july-mosa-intensive-2026-230"]
    assert mosa._parse_event_urls(raw_xml) == expected  # gala dropped, about-us ignored
    assert mosa._parse_event_urls(rendered) == expected


# --- dates: Odoo ISO <time data-oe-expression> --------------------------------


def test_dates_from_oe_time_nodes():
    html = """
    <time datetime="2026-08-10 07:00:00" data-oe-expression="event.date_begin">09:00</time>
    <time datetime="2026-08-22 17:00:00" data-oe-expression="event.date_end">19:00</time>
    """
    assert mosa._dates(HTMLParser(html)) == (date(2026, 8, 10), date(2026, 8, 22))


def test_dates_absent():
    assert mosa._dates(HTMLParser("<p>no event time nodes here</p>")) == (None, None)


# --- ages: clean title/slug, noisy body needs an "aged" cue -------------------


def test_age_from_title():
    assert mosa._age_range("August Signature Intensive Course 2026 (age 12-29)") == {
        "min": 12,
        "max": 29,
    }


def test_age_body_fallback_requires_aged_cue():
    # "3 to 6 people" (shared room) in the body must NOT become an age range.
    body = "Shared room (3 to 6 people). For dancers aged 12 to 21."
    assert mosa._age_range("July Mosa Intensive 2026", body) == {"min": 12, "max": 21}


def test_age_none_when_only_room_numbers():
    assert mosa._age_range("July Mosa Intensive 2026", "Shared room (3 to 6 people).") is None


# --- prices: one Price per Odoo ticket, from Offer microdata ------------------

_TICKETS = """
<div class="o_wevent_ticket_selector">
  <div itemscope itemtype="http://schema.org/Offer">
    <h5 itemprop="name">6-DAY PROGRAM August Signature 2026 - Lunch Included (10/08-15/08)</h5>
  </div>
  <span class="oe_currency_value">749,00</span>&nbsp;&euro;
  <span itemprop="price" class="d-none">749.0</span>
  <span itemprop="priceCurrency" class="d-none">EUR</span>
</div>
<div class="o_wevent_ticket_selector">
  <div itemscope itemtype="http://schema.org/Offer">
    <h5 itemprop="name">12-DAY PROGRAM August Signature 2026 - Lunch Included (10/08-22/08)</h5>
  </div>
  <span itemprop="price" class="d-none">1299.0</span>
  <span itemprop="priceCurrency" class="d-none">EUR</span>
</div>
"""


def test_prices_from_ticket_microdata():
    prices = mosa._prices(HTMLParser(_TICKETS))
    assert [(p.amount, p.currency, p.includes) for p in prices] == [
        (749.0, "EUR", ["tuition", "meals"]),  # "Lunch Included" -> meals
        (1299.0, "EUR", ["tuition", "meals"]),
    ]
    assert prices[0].label is not None
    assert prices[0].label.startswith("6-DAY PROGRAM")


def test_prices_none_when_no_tickets():
    assert mosa._prices(HTMLParser("<div>Anmeldungen geschlossen</div>")) == []


_SINGLE_TICKET = """
<div class="o_wevent_registration_single">
  <h5 itemprop="name" class="my-0 pe-3 o_wevent_single_ticket_name">
    July Mosa Intensive 2026
  </h5>
  <span class="badge text-bg-secondary fs-6">
    <span class="oe_currency_value">1,000.00</span>&nbsp;€
  </span>
  <span itemprop="price" class="d-none">1000.0</span>
  <span itemprop="priceCurrency" class="d-none">EUR</span>
</div>
"""


def test_prices_from_single_ticket_widget():
    prices = mosa._prices(HTMLParser(_SINGLE_TICKET))
    assert len(prices) == 1
    assert prices[0].amount == 1000.0
    assert prices[0].currency == "EUR"
    assert "tuition" in prices[0].includes


# --- status: read from the Odoo registration widget ---------------------------


def test_status_open_when_tickets_present():
    assert mosa._status(HTMLParser(_TICKETS)) == "open"


def test_status_closed_banner_en_and_de():
    assert (
        mosa._status(HTMLParser("<body><div class='alert'>Registrations closed</div></body>"))
        == "closed"
    )
    assert (
        mosa._status(HTMLParser("<body><div class='alert'>Anmeldungen geschlossen</div></body>"))
        == "closed"
    )


def test_status_none_when_unstated():
    assert mosa._status(HTMLParser("<body><p>An intensive course.</p></body>")) is None


def test_status_open_when_single_ticket_widget_present():
    # The July MOSA Intensive uses a single-ticket widget instead of the
    # multi-ticket selector — both must be detected as "open".
    assert mosa._status(HTMLParser(_SINGLE_TICKET)) == "open"
