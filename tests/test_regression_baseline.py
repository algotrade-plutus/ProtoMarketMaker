"""Naive-arm regression pins on the RIVF'26 frozen slices.

The published IS/OOS anchor (manifest ``expected``) was computed on the
Drive CSVs under ``data/is`` / ``data/os``, which are not in this checkout; that
check runs only where they are present. The RIVF'26 naive anchor is pinned here
on the committed slices, exactly, so any change to the engine or the seam shows.
"""
import os
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

DATA = Path(__file__).resolve().parents[1] / "data"

PINS = {
    # window: (hpr, sharpe, fills, round_trips, end equity in dong)
    "im2022": (-0.12932, -1.7421722944332323, 129, 64, 435_340_000.0),
    "krx2025": (0.29567999999999994, 1.6082487716307658, 693, 345, 647_840_000.0),
}


@pytest.mark.parametrize("window", sorted(PINS))
def test_naive_anchor_on_slice_is_pinned(window):
    if not (DATA / "l2" / window / "local_quote_matched.parquet").exists():
        pytest.skip(f"needs the frozen {window} slice")
    from proto_market_maker.experiments import mm_anchor as m
    fcc, sessions = m.load_contract_map(window)
    n = m.run_naive(window, sessions, fcc, m.step_param())
    hpr, sharpe, fills, rts, end = PINS[window]
    assert (n["hpr"], n["sharpe"], n["fills"], n["round_trips"], n["end_equity_dong"]) \
        == (hpr, sharpe, fills, rts, end)


HAS_IS = os.path.exists("data/is/VN30F1M_data.csv")


@pytest.mark.skipif(not HAS_IS, reason="needs the published Drive CSVs under data/is")
def test_in_sample_reproduces_published():  # pragma: no cover - data-gated
    from proto_market_maker.backtest import Backtesting
    bt = Backtesting(capital=Decimal("5e5"), printable=False)
    bt.run(bt.process_data(evaluation=False), Decimal("1.8"))
    sharpe = float(bt.metric.sharpe_ratio(risk_free_return=Decimal("0.00023")) * Decimal(np.sqrt(250)))
    assert sharpe == pytest.approx(0.9516979860670635, rel=1e-12)
