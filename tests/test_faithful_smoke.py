"""The faithful arm runs one session end to end on the shipped slice."""
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"
HAS = (DATA / "l2" / "im2022" / "local_quote_total.parquet").exists()


@pytest.mark.skipif(not HAS, reason="needs the frozen im2022 slice under data/")
@pytest.mark.parametrize("queue", ["conservative", "optimistic"])
def test_faithful_one_session_runs_and_closes_out(queue):
    from proto_market_maker.experiments import mm_anchor as m
    fcc, sessions = m.load_contract_map("im2022")
    out = m.run_faithful("im2022", sessions, fcc, m.step_param(), queue,
                         days=sessions[1:2], log=lambda *_: None)
    assert out["sessions"] == 1
    assert out["submitted"] > 100                 # it quoted the whole session
    assert out["forced_liquidations"] == 0
    assert len(out["capacity"]) == 1 and out["capacity"][0]["rate"] == "0.13"
    s = out["per_session"][0]
    assert "refused" not in s                     # pre-KRX: margin model resolves


def test_regime_guard_refuses_post_krx():
    from datetime import date
    from proto_market_maker.experiments.mm_anchor import _margin_model_ok
    assert _margin_model_ok(date(2025, 5, 2)) is True
    assert _margin_model_ok(date(2025, 5, 5)) is False
