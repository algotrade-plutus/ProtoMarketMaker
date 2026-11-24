"""The naive fill tracer records what each rung books, without changing A."""
from datetime import date
from decimal import Decimal

from proto_market_maker.experiments.mm_fills_trace import _naive_tracer_class
from proto_market_maker.naive_variants import NaiveOptions, NaiveVariant
from tests.test_naive_variants import BUY_ONLY, CAP, STEP, frame

DAY = date(2022, 11, 21)


def _trace(n):
    bt = _naive_tracer_class()(CAP, NaiveOptions.rung(n), {DAY: ("F1", "F2")}, lambda *_: None)
    bt.run(frame(BUY_ONLY, DAY), STEP)
    return bt


def test_trace_records_the_booked_price_per_rung_and_leaves_the_run_unchanged():
    for n, booked in ((0, "995.0"), (1, "996.9")):
        bt = _trace(n)
        ref = NaiveVariant(CAP, NaiveOptions.rung(n))
        ref.run(frame(BUY_ONLY, DAY), STEP)
        assert bt.daily_assets == ref.daily_assets and bt.inventory == ref.inventory
        assert len(bt.trace) == 1
        f = bt.trace[0]
        assert (f["side"], Decimal(f["price"]), f["qty"], f["maker"], f["role"], f["ticker"]) == \
               ("BUY", Decimal(booked), 1, True, "quote", "F1")
        assert Decimal(f["limit"]) == Decimal("996.9")
        s = bt.per_session[0]
        assert s["positions"] == {"F1": 1} and s["end_equity_dong"] == float(ref.daily_assets[-1]) * 1000
