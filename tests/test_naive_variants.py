"""One test per naive ladder rung (``naive_variants``, N1-N3), each on a tiny
synthetic tick stream run through A's own loop (``Backtesting.run``), plus:
the default naive engine is unchanged."""
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from proto_market_maker.backtest import Backtesting, FEE_PER_CONTRACT
from proto_market_maker.naive_variants import (NaiveOptions, NaiveVariant,
                                               vsd_initial_margin_rate)

STEP = Decimal("3.1")
CAP = Decimal("5e5")
D = Decimal


def frame(prices, day=date(2022, 11, 21)):
    """A one-session row stream in ``Backtesting.prepare``'s layout."""
    rows = []
    for i, p in enumerate(prices):
        rows.append({"datetime": pd.Timestamp(datetime(day.year, day.month, day.day, 9, i)),
                     "date": day, "tickersymbol": "F1", "price": D(p),
                     "close": D(prices[-1]), "f2_price": D(p) - 1,
                     "f2_close": D(prices[-1]) - 1})
    return pd.DataFrame(rows)


# 09:00 print 1000.0 -> quote 996.9 / 1003.1; 09:01 print 995.0 crosses the bid
BUY_ONLY = ["1000.0", "995.0"]


# N1 -------------------------------------------------------------------------
def test_n1_bid_crossed_by_lower_print_books_at_the_bid():
    for n, booked in ((0, D("995.0")), (1, D("996.9"))):
        bt = NaiveVariant(CAP, NaiveOptions.rung(n))
        bt.run(frame(BUY_ONLY), STEP)
        assert bt.inventory == 1 and bt.fills == 1
        # update_pnl marks at the close (995.0): the booked price is the loss basis
        assert bt.daily_assets[-1] - CAP == (D("995.0") - booked) * 100


# N2 -------------------------------------------------------------------------
def test_n2_dated_vsd_rate():
    assert vsd_initial_margin_rate(date(2022, 12, 14)) == D("0.13")
    assert vsd_initial_margin_rate(date(2022, 12, 15)) == D("0.17")
    price = D("1000.0")
    # 500,000 / (1000 * 100 * rate): 29 at 17%, 38 at 13%
    for day, n_flat, n_dated in ((datetime(2022, 12, 14, 9), 29, 38),
                                 (datetime(2022, 12, 15, 9), 29, 29)):
        flat = NaiveVariant(CAP, NaiveOptions.rung(1)); flat.cur_date = day
        dated = NaiveVariant(CAP, NaiveOptions.rung(2)); dated.cur_date = day
        assert flat.get_maximum_placeable(price) == n_flat
        assert dated.get_maximum_placeable(price) == n_dated


# N3 -------------------------------------------------------------------------
def test_n3_fee_charged_on_opening_fill():
    for n, fee in ((2, D("0")), (3, FEE_PER_CONTRACT)):
        bt = NaiveVariant(CAP, NaiveOptions.rung(n))
        bt.run(frame(BUY_ONLY), STEP)
        assert bt.inventory == 1                       # an opening fill only
        assert bt.daily_assets[-1] - CAP == (D("995.0") - D("996.9")) * 100 - fee


# default unchanged ------------------------------------------------------------
def _two_days():
    a = frame(["1000.0", "995.0", "1004.0", "996.0", "1001.0"], date(2022, 11, 17))
    b = frame(["1002.0", "1006.0", "998.0", "1003.0", "997.5"], date(2022, 11, 18))
    return pd.concat([a, b], ignore_index=True)


def test_default_options_reproduce_the_base_engine():
    base = Backtesting(CAP, printable=False)
    base.run(_two_days(), STEP)
    var = NaiveVariant(CAP)                      # all options off
    var.run(_two_days(), STEP)
    assert var.daily_assets == base.daily_assets
    assert var.daily_inventory == base.daily_inventory
    assert var.fills > 0


def test_backtest_module_has_no_variant_hooks():
    assert not hasattr(Backtesting, "options")
    assert NaiveOptions.rung(0) == NaiveOptions()
