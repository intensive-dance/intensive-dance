"""Unit tests for the Centrum Sztuki Tańca scraper (Kraków summer intensives).

The body is Polish in every render, so these pin the language-agnostic parse:
the two summer-camp turnusy (distinct dates + venues from one page), the DANCEit
14+ teen intensive (open-ended age, named guest), the PLN residential fee, and
the technique-keyed genres. Inputs are the plain-text shape the scraper feeds its
helpers (the live pages flatten to this). Inline strings, no network.
"""

from __future__ import annotations

from datetime import date

from intensive_dance.scrapers import centrum_sztuki_tanca as cst

# Trimmed but faithful to the live `/letnie-obozy-baletowe-2026/` page text.
CAMP = (
    "Letnie obozy baletowe 2026! Where Little Stars rise! TERMINY "
    "I turnus: 12 – 19.07.2026 (8 dni) | Dom Wczasowy Oliwia, Małe Ciche "
    "II turnus: 19 – 26.08.2026 (8 dni) | Dom Wczasowy Jędrol, Suche "
    "PROGRAM Program taneczny Balet Taniec współczesny Jazz Stretching Flamenco "
    "CENA Turnus I: Małe Ciche: 2 400 zł / cena dla Rodzeństwa: 2 350 zł od osoby "
    "Każda inna dieta niż zwykła dodatkowo płatna: 105 zł / os. "
    "Cena zawiera: 7 noclegów, posiłki, transport autokarem Kraków – Małe Ciche."
)

# Trimmed but faithful to the live `/danceit-2026/` page text.
DANCEIT = (
    "DANCEit 2026 – Letnie Warsztaty Taneczne dla Młodzieży 14+ "
    "TERMIN 19 – 26.08.2026 Miejsce: Dom Wczasowy Jędrol, Suche "
    "tancerki i tancerzy od 14 roku życia. PROGRAM: taniec współczesny, "
    "taniec klasyczny, jazz, partnerowanie, stretching. "
    "Pierwszym gościem będzie wspaniała Sandra Szatan! "
    "CENA: 2 600 zł Dieta wegetariańska dodatkowo płatna: 70 zł / os."
)


def test_full_build_emits_three_offerings():
    offs = cst._build_offerings(CAMP, DANCEIT, date(2026, 6, 8))
    assert [o.id for o in offs] == [
        "centrum-sztuki-tanca/danceit-2026-08-19",
        "centrum-sztuki-tanca/letnie-oboz-baletowy-2026-07-12",
        "centrum-sztuki-tanca/letnie-oboz-baletowy-2026-08-19",
    ]


def test_camp_two_turnusy_distinct_dates_and_venues():
    offs = cst._build_camp_offerings(CAMP)
    assert len(offs) == 2
    first, second = sorted(offs, key=lambda o: o.id)
    assert first.schedule.start == date(2026, 7, 12)
    assert first.schedule.end == date(2026, 7, 19)
    assert first.location is not None
    assert first.location.venue == "Dom Wczasowy Oliwia"
    assert first.location.city == "Małe Ciche"
    assert second.schedule.start == date(2026, 8, 19)
    assert second.location is not None
    assert second.location.venue == "Dom Wczasowy Jędrol"
    assert second.location.city == "Suche"
    assert second.location.country == "PL"


def test_camp_price_is_headline_pln_not_surcharge():
    [price] = cst._prices(CAMP)
    assert price.amount == 2400.0
    assert price.currency == "PLN"
    assert price.includes == ["tuition", "accommodation", "meals"]


def test_camp_has_no_stated_age():
    offs = cst._build_camp_offerings(CAMP)
    assert all(o.age_range is None for o in offs)


def test_danceit_age_open_ended_14_plus():
    off = cst._build_danceit_offering(DANCEIT)
    assert off is not None
    assert off.age_range == {"min": 14}  # null upper bound (open-ended)


def test_danceit_price_and_guest():
    off = cst._build_danceit_offering(DANCEIT)
    assert off is not None
    assert [p.amount for p in off.prices] == [2600.0]
    assert [t.name for t in off.teachers] == ["Sandra Szatan"]
    assert off.teachers[0].role == "guest"


def test_genres_from_programme_drop_out_of_scope():
    # Balet/klasyczny → classical, współczesny → contemporary; jazz/flamenco/
    # stretching have no Genre-enum slot and drop out.
    assert cst._genres(CAMP) == ["classical", "contemporary"]
    assert cst._genres(DANCEIT) == ["classical", "contemporary"]


def test_danceit_missing_dates_returns_none():
    assert cst._build_danceit_offering("DANCEit — daty wkrótce.") is None
