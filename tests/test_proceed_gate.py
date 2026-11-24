"""Pre-registered proceed gate (activity / credibility only, never P&L).

* naive arm: >= 300 completed round trips over the experiment windows;
* faithful arm: no unbounded margin-liquidation cascade
  (forced liquidations <= sessions, per window).

Reads the committed ``result/mm_anchor/<window>.json`` written by
``python -m proto_market_maker.experiments.mm_anchor <window>``. If the gate
fails, the result is reported as is; the threshold is not changed.
"""
import json
from pathlib import Path

import pytest

RESULT = Path(__file__).resolve().parents[1] / "result" / "mm_anchor"
WINDOWS = ("krx2025", "im2022")


def _load():
    out = {}
    for w in WINDOWS:
        p = RESULT / f"{w}.json"
        if not p.exists():
            pytest.skip(f"needs {p.name}; run the mm_anchor runner first")
        out[w] = json.loads(p.read_text())
    return out


def test_naive_round_trips_at_least_300():
    res = _load()
    total = sum(r["naive"]["round_trips"] for r in res.values())
    assert total >= 300, f"kill: only {total} naive round trips"


def test_faithful_has_no_liquidation_cascade():
    for w, r in _load().items():
        f = r["faithful"]
        assert f["forced_liquidations"] <= f["sessions"], f"{w}: cascade"
