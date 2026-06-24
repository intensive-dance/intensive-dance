"""Offline tests for model-level derivations (no network)."""

from __future__ import annotations

from intensive_dance.models import Price, _classify_price_type


def test_tuition_tag_wins_over_a_fee_ish_label():
    # an explicit tuition tag beats a fee-ish word in the label ("Participation
    # fee", "Forfait stage" are really the course price, just labelled oddly)
    assert _classify_price_type(["tuition"], "Participation fee") == "tuition"
    assert _classify_price_type(["tuition", "accommodation"], "Tuition (full board)") == "tuition"


def test_registration_fee_from_label():
    assert _classify_price_type([], "Registration fee") == "registration"
    assert _classify_price_type([], "Application fee") == "registration"
    assert _classify_price_type([], "Anmeldegebühr") == "registration"


def test_deposit_takes_precedence_over_registration():
    assert _classify_price_type([], "Deposit (non-refundable)") == "deposit"


def test_standalone_accommodation_and_meals():
    assert _classify_price_type(["accommodation"], "Housing (per week)") == "accommodation"
    assert _classify_price_type([], "Meal Plans (per week)") == "meals"


def test_unclassifiable_is_other():
    assert _classify_price_type([], None) == "other"
    assert _classify_price_type([], "Total cost") == "other"


def test_price_auto_derives_type_but_explicit_wins():
    assert Price(amount=29, currency="EUR", label="Registration fee").type == "registration"
    assert Price(amount=500, currency="EUR", includes=["tuition"]).type == "tuition"
    # a type set by the scraper is respected, never overridden by the derivation
    assert Price(amount=1, currency="EUR", label="Registration fee", type="other").type == "other"
