"""Markout, liquidity, price-improvement and carry/trading arithmetic
(``experiments.mm_markout``) on a tiny synthetic fill list. Pure: no data, no
engine."""
import json
from datetime import date, datetime

import pytest

from proto_market_maker.experiments.mm_markout import (
    MULT, Fill, PricePath, decompose, infer_tickers, load_fills, markouts,
    price_improvement, summarise)

D0 = date(2022, 11, 21)


def t(h, m, s=0):
    return datetime(D0.year, D0.month, D0.day, h, m, s)


PATH = PricePath({"F1": [(t(9, 0), 1000.0), (t(9, 1), 1002.0), (t(9, 5), 998.0),
                         (t(9, 10), 1001.0)],
                  "F2": [(t(9, 0), 990.0), (t(9, 10), 991.0)]})
CLOSES = {(D0, "F1"): 1005.0, (D0, "F2"): 995.0}

BUY = Fill(ts=t(9, 0), ticker="F1", side="BUY", price=999.0, qty=1, maker=True,
           limit=999.0, role="quote")
SELL = Fill(ts=t(9, 0, 30), ticker="F1", side="SELL", price=1001.0, qty=2, maker=False,
            limit=1000.0, role="quote")


def test_price_path_is_last_print_at_or_before():
    assert PATH.at("F1", t(9, 0, 59)) == 1000.0
    assert PATH.at("F1", t(9, 1)) == 1002.0
    assert PATH.at("F1", t(8, 59)) == 1000.0          # before the first print: the first
    assert PATH.at("F1", t(14, 0)) == 1001.0


def test_markouts_per_contract_signed_by_side():
    # BUY 999: +1m 1002 -> +3; +5m 998 -> -1; close 1005 -> +6
    assert markouts(BUY, PATH, CLOSES) == {"1m": 3.0, "5m": -1.0, "close": 6.0}
    # SELL 1001: +1m (09:01:30) 1002 -> -1; +5m (09:05:30) 998 -> +3; close -> -4
    assert markouts(SELL, PATH, CLOSES) == {"1m": -1.0, "5m": 3.0, "close": -4.0}


def test_price_improvement_vs_own_limit():
    assert price_improvement(BUY) == 0.0
    assert price_improvement(SELL) == 1.0             # sold 1 point above the limit
    assert price_improvement(Fill(t(9, 0), "F1", "BUY", 998.5, 1, False, 999.0, "quote")) == 0.5
    assert price_improvement(Fill(t(9, 0), "F1", "BUY", 998.5, 1, False, None, "quote")) is None


def test_summarise_weights_by_contracts():
    s = summarise([BUY, SELL], PATH, CLOSES)
    assert s["fills"] == 2 and s["contracts"] == 3
    assert s["markout_mean_points"]["1m"] == pytest.approx((3 - 2) / 3)
    assert s["markout_mean_points"]["5m"] == pytest.approx((-1 + 6) / 3)
    assert s["markout_mean_points"]["close"] == pytest.approx((6 - 8) / 3)
    assert s["markout_total_points"]["5m"] == pytest.approx(5.0)
    assert s["markout_total_dong"]["5m"] == pytest.approx(5.0 * MULT)
    assert s["taker_share"] == pytest.approx(2 / 3)
    assert s["by_liquidity"]["taker"]["contracts"] == 2
    assert s["by_liquidity"]["maker"]["markout_mean_points"]["5m"] == pytest.approx(-1.0)
    pi = s["price_improvement_points"]
    assert pi["n"] == 1 and pi["median"] == 1.0 and pi["sum"] == 1.0
    assert s["by_role"] == {"quote": 3}


def test_summarise_unknown_liquidity_is_not_counted_as_maker():
    f = Fill(t(9, 0), "F1", "BUY", 999.0, 1, None, 999.0, "quote")
    s = summarise([f, SELL], PATH, CLOSES)
    assert s["taker_share"] == pytest.approx(1.0)     # 2 of the 2 contracts with a known side
    assert s["by_liquidity"]["unknown"]["contracts"] == 1


def test_decompose_carry_is_prior_position_times_close_move():
    days = [D0, date(2022, 11, 22), date(2022, 11, 23)]
    closes = {(days[0], "F1"): 1000.0, (days[1], "F1"): 1010.0, (days[2], "F1"): 1004.0}
    pnl = [1e5, 2.5e6, 4e5]
    pos = [{"F1": 2}, {"F1": -1}, {}]
    out = decompose(days, pnl, pos, closes)
    assert out["carry_dong"] == pytest.approx(2 * 10 * MULT + (-1) * (-6) * MULT)
    assert out["trading_dong"] == pytest.approx(sum(pnl) - out["carry_dong"])
    assert out["total_dong"] == pytest.approx(sum(pnl))
    assert out["carry_missing_close"] == 0
    assert [r["carry_dong"] for r in out["per_session"]] == pytest.approx([0, 2e6, 6e5])


def test_decompose_counts_a_missing_close_and_books_no_carry():
    days = [D0, date(2022, 11, 22)]
    out = decompose(days, [0.0, 1e6], [{"F1": 1}, {}], {(days[0], "F1"): 1000.0})
    assert out["carry_dong"] == 0 and out["carry_missing_close"] == 1
    assert out["trading_dong"] == 1e6


def test_infer_tickers_picks_the_contract_priced_nearest_the_fill():
    f = Fill(t(9, 2), None, "SELL", 989.0, 1, False, 989.0, "unknown")
    g = Fill(t(9, 2), None, "BUY", 1003.0, 1, True, 1003.0, "unknown")
    out, n_ambiguous = infer_tickers([f, g], PATH, lambda ts: ("F1", "F2"))
    assert [x.ticker for x in out] == ["F2", "F1"] and n_ambiguous == 0


def test_load_fills_reads_the_scratch_trace_format(tmp_path):
    rows = [{"ts": "2022-11-21 09:00:00.5", "side": "SELL", "limit": "958.7",
             "price": "958.900000", "qty": 1, "maker": False, "detail_keys": [], "detail": {}},
            {"ts": "2022-11-21 09:01:00", "side": "BUY", "limit": None, "price": "957.0",
             "qty": 3, "maker": True, "ticker": "VN30F2212", "role": "roll"}]
    p = tmp_path / "fills.json"
    p.write_text(json.dumps(rows))
    a, b = load_fills(p)
    assert a.ticker is None and a.role == "unknown" and a.maker is False
    assert a.price == 958.9 and a.limit == 958.7 and a.ts == datetime(2022, 11, 21, 9, 0, 0, 500000)
    assert b.ticker == "VN30F2212" and b.role == "roll" and b.qty == 3 and b.limit is None
    # the committed trace format wraps the list: {"fills": [...], ...}
    p.write_text(json.dumps({"fills": rows}))
    assert len(load_fills(p)) == 2
