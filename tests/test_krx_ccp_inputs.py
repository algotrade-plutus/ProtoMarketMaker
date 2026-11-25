"""krx2025 carries what the engine's post-KRX CCP layer reads (plutus-simulator 4867d46)."""
import csv
import json
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLOSE = ROOT / "data" / "band" / "krx2025" / "quote_close.parquet"
LADDER = ROOT / "result" / "mm_ladder" / "krx2025.json"


@pytest.mark.skipif(not CLOSE.exists(), reason="needs the frozen krx2025 slice under data/")
def test_vn30_index_close_on_every_krx2025_session_and_not_im2022():
    import pandas as pd
    with open(ROOT / "data" / "market" / "krx2025" / "futurecontractcode.csv", encoding="utf-8") as fh:
        sessions = sorted({date.fromisoformat(r["datetime"]) for r in csv.DictReader(fh)})
    c = pd.read_parquet(CLOSE)
    vn30 = sorted(pd.to_datetime(c[c["tickersymbol"] == "VN30"]["datetime"]).dt.date)
    assert vn30 == sessions and len(sessions) == 40
    im = pd.read_parquet(ROOT / "data" / "band" / "im2022" / "quote_close.parquet")
    assert "VN30" not in set(im["tickersymbol"])      # pre-KRX margin never reads it


@pytest.mark.skipif(not LADDER.exists(), reason="needs result/mm_ladder/krx2025.json")
def test_ccp_layer_decided_every_post_cutover_night_and_views_are_consistent():
    doc = json.loads(LADDER.read_text())
    rungs = {r["rung"]: r for r in doc["rungs"]}
    for arm in ("F-opt", "F-con"):
        assert rungs[arm]["ccp_nights"] > 0
        assert rungs[arm]["ccp_indeterminate_nights"] == 0
        assert rungs[arm]["ccp_calendar_spread_unknown"] == 0
    assert all(doc["views"]["pre_cutover"]["naive_cut_equals_pre_only_run"].values())
    pre = {r["rung"]: r for r in doc["views"]["pre_cutover"]["rungs"]}
    post = {r["rung"]: r for r in doc["views"]["post_cutover"]["rungs"]}
    for k, r in rungs.items():
        assert pre[k]["fills"] + post[k]["fills"] == r["fills"]
        assert (1 + pre[k]["hpr"]) * (1 + post[k]["hpr"]) == pytest.approx(1 + r["hpr"], rel=1e-12)
