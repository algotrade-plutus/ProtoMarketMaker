"""The paper kit and the report read their numbers from the committed result files."""
import json
from pathlib import Path

import pytest

RESULT = Path(__file__).resolve().parents[1] / "result"
HAS = (RESULT / "mm_ladder" / "im2022.json").exists() and (RESULT / "mm_ladder" / "krx2025.json").exists()


@pytest.mark.skipif(not HAS, reason="needs result/mm_ladder")
def test_kit_values_come_from_the_ladder_files(tmp_path):
    from proto_market_maker.experiments.mm_paper_kit import build
    kit = build(RESULT, tmp_path)
    for w in ("im2022", "krx2025"):
        doc = json.loads((RESULT / "mm_ladder" / f"{w}.json").read_text())
        hpr = {r["rung"]: r["hpr"] for r in doc["rungs"]}
        got = {k: v["hpr"] for k, v in kit["ladder"][w]["rungs"].items()}
        assert got == hpr
        assert kit["ladder"][w]["band"] == {"low": min(hpr["F-con"], hpr["F-opt"]),
                                            "high": max(hpr["F-con"], hpr["F-opt"])}
    for f in ("mm_ladder.pdf", "mm_ladder.png", "mm_ladder.tex", "mm_ladder.md"):
        assert (tmp_path / f).stat().st_size > 0
    tex = (tmp_path / "mm_ladder.tex").read_text()
    assert f"${100 * hpr['F-con']:+.2f}$" in tex          # krx2025 F-con, read not typed


@pytest.mark.skipif(not HAS, reason="needs result/mm_ladder")
def test_report_carries_the_ladder_values():
    from proto_market_maker.experiments.mm_report import build
    md = build(RESULT)
    doc = json.loads((RESULT / "mm_ladder" / "im2022.json").read_text())
    for r in doc["rungs"]:
        assert f"{100 * r['hpr']:+.2f}%" in md
    assert "/Users/" not in md and "/private/" not in md
