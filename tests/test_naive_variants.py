"""One test per attribution-ladder rung (``naive_variants``), on tiny synthetic
tick streams, plus: the default naive engine is unchanged."""
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from proto_market_maker.backtest import Backtesting, FEE_PER_CONTRACT
from proto_market_maker.naive_variants import (NaiveOptions, NaiveVariant,
                                               vsd_initial_margin_rate)

STEP = Decimal("3.1")
CAP = Decimal("5e5")
D = Decimal


def ts(day, hms):
    h, m, s = map(int, hms.split(":"))
    return datetime(day.year, day.month, day.day, h, m, s)


def one_buy_session(day, close_print=True, close=D("998.0")):
    # 09:00 print 1000.0 -> quote 996.9 / 1003.1; 09:00:05 print 995.0 crosses the bid
    ticks = [(ts(day, "09:00:00"), D("1000.0")), (ts(day, "09:00:05"), D("995.0"))]
    if close_print:
        ticks.append((ts(day, "14:25:10"), D("999.0")))
    return (day, "VN30FTEST", ticks, close)


# rung 1 ---------------------------------------------------------------------
def test_rung1_no_inventory_carried_past_the_session():
    d1, d2 = date(2022, 11, 17), date(2022, 11, 18)
    bt = NaiveVariant(CAP, NaiveOptions.rung(1))
    # session 1 closes out at the 14:25:10 print; session 2 has no print at or
    # after 14:25, so its residual is marked at the close. Both end flat.
    bt.run_sessions([one_buy_session(d1), one_buy_session(d2, close_print=False)], STEP)
    assert bt.daily_inventory == [0, 0]
    assert bt.inventory == 0
    assert bt.closeout_contracts == 1 and bt.marked_contracts == 1
    # session 1: bought 1 at the print 995.0, sold at 999.0: +4 pt * 100 - fee (closing)
    assert bt.daily_assets[1] - bt.daily_assets[0] == D("400") - FEE_PER_CONTRACT


def test_rung1_stops_quoting_at_1425():
    d = date(2022, 11, 17)
    bt = NaiveVariant(CAP, NaiveOptions.rung(1))
    # the 14:25:00 print would cross the 09:00 bid, but quoting has stopped
    ticks = [(ts(d, "09:00:00"), D("1000.0")), (ts(d, "14:25:00"), D("990.0"))]
    bt.run_sessions([(d, "VN30FTEST", ticks, D("990.0"))], STEP)
    assert bt.fills == 0 and bt.daily_assets[-1] == CAP


# rung 2 ---------------------------------------------------------------------
def test_rung2_bid_crossed_by_lower_print_books_at_the_bid():
    d = date(2022, 11, 17)
    for n, booked in ((1, D("995.0")), (2, D("996.9"))):
        bt = NaiveVariant(CAP, NaiveOptions.rung(n))
        day, tk, ticks, close = one_buy_session(d, close_print=False)
        bt.handle_force_sell(ticks[0][1])
        bt.cur_date = ticks[0][0]
        bt.update_bid_ask(ticks[0][1], STEP, ticks[0][0])
        assert bt.bid_price == D("996.9")
        bt.cur_date = ticks[1][0]
        bt.update_bid_ask(ticks[1][1], STEP, ticks[1][0])
        assert bt.inventory == 1 and bt.inventory_price == booked


# rung 3 ---------------------------------------------------------------------
def test_rung3_dated_vsd_rate():
    assert vsd_initial_margin_rate(date(2022, 12, 14)) == D("0.13")
    assert vsd_initial_margin_rate(date(2022, 12, 15)) == D("0.17")
    price = D("1000.0")
    for day, n_flat, n_dated in ((datetime(2022, 12, 14, 9), 29, 38),
                                 (datetime(2022, 12, 15, 9), 29, 29)):
        flat = NaiveVariant(CAP, NaiveOptions.rung(2)); flat.cur_date = day
        dated = NaiveVariant(CAP, NaiveOptions.rung(3)); dated.cur_date = day
        # 500,000 / (1000 * 100 * rate)
        assert flat.get_maximum_placeable(price) == n_flat
        assert dated.get_maximum_placeable(price) == n_dated


# rung 4 ---------------------------------------------------------------------
def test_rung4_fee_charged_on_opening_fill():
    d = date(2022, 11, 17)
    for n, fee in ((3, D("0")), (4, FEE_PER_CONTRACT)):
        bt = NaiveVariant(CAP, NaiveOptions.rung(n))
        _, _, ticks, _ = one_buy_session(d, close_print=False)
        for t, p in ticks:
            bt.cur_date = t
            bt.update_bid_ask(p, STEP, t)
        assert bt.inventory == 1           # an opening fill only
        assert bt.ac_loss == fee


# default unchanged ------------------------------------------------------------
def _frame():
    rows = []
    prices = {date(2022, 11, 17): ["1000.0", "995.0", "1004.0", "996.0", "1001.0"],
              date(2022, 11, 18): ["1002.0", "1006.0", "998.0", "1003.0", "997.5"]}
    for day, ps in prices.items():
        for i, p in enumerate(ps):
            rows.append({"datetime": pd.Timestamp(ts(day, f"09:{i:02d}:00")), "date": day,
                         "tickersymbol": "F1", "price": D(p), "close": D(ps[-1]),
                         "f2_price": D(p) - 1, "f2_close": D(ps[-1]) - 1})
    return pd.DataFrame(rows)


def test_default_options_reproduce_the_base_engine():
    base = Backtesting(CAP, printable=False)
    base.run(_frame(), STEP)
    var = NaiveVariant(CAP)                      # all options off, base run()
    var.run(_frame(), STEP)
    assert var.daily_assets == base.daily_assets
    assert var.daily_inventory == base.daily_inventory
    assert var.fills > 0


def test_backtest_module_has_no_variant_hooks():
    # the variants live in a subclass; backtest.Backtesting itself is untouched
    assert not hasattr(Backtesting, "options")
    assert NaiveOptions.rung(0) == NaiveOptions()
