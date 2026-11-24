from decimal import Decimal

from proto_market_maker.strategy import quote


def test_quote_flat_inventory_is_symmetric_step_around_price():
    assert quote(Decimal("1000.0"), 0, Decimal("3.1")) == (Decimal("996.9"), Decimal("1003.1"))


def test_quote_long_inventory_skews_bid_down_ask_unchanged():
    assert quote(Decimal("1000.0"), 5, Decimal("3.1")) == (Decimal("996.6"), Decimal("1003.1"))


def test_quote_short_inventory_skews_ask_down_bid_unchanged():
    assert quote(Decimal("1000.0"), -5, Decimal("3.1")) == (Decimal("996.9"), Decimal("1003.4"))
