"""MarketMaker attribution ladder (RIVF'26 camera-ready).

Attributes the naive -> faithful gap of ``mm_anchor`` one rung at a time. The
design mismatches between the two arms are closed first (rung 1), then
execution realism is added one rule per rung. Report, don't tune: every rung
runs the same ``strategy.quote`` at the optimized ``step`` (3.1).

====  =====================================================================
rung  rule
====  =====================================================================
0     naive engine as-is (``mm_anchor.run_naive``)
1     + aligned: flat every session (quote 09:00-14:25, close the residual at
      the first print >= 14:25), traded contract's own prints only
      (``windows.traded_contracts``), no overnight inventory / synthetic roll
2     + own-price fills (a crossed quote books at the bid/ask, not the print)
3     + dated VSD IM (13% before 2022-12-15, 17% from it)
4     + fee on every fill (opening fills too)
5     faithful arm, optimistic queue   (read from ``result/mm_anchor``)
6     faithful arm, conservative queue (read from ``result/mm_anchor``)
7     krx2025 only: the 20 post-cutover sessions the regime guard refuses
====  =====================================================================

Rungs 0-4 are the pure naive engine (``naive_variants``; no plutus import).
Rungs 5-7 are read from ``result/mm_anchor/<window>.json`` (its sha256 and
the plutus-simulator commit it records are written out), not re-run. For
krx2025 every rung is on the 20 **pre-cutover** sessions: the faithful arm
refuses the post-cutover sessions and books them flat, so its whole-window
fills and HPR are exactly its pre-cutover numbers (checked below from its
per-session equity). Faithful round trips are not stored in the anchor JSON;
every faithful session ends flat (closed out or marked), so
``round_trips = (fills - closeout_marked_contracts) / 2`` exactly.

Units: real dong (naive thousand-dong x 1000), as ``mm_anchor``.

Run::

    .venv/bin/python -m proto_market_maker.experiments.mm_ladder krx2025
    .venv/bin/python -m proto_market_maker.experiments.mm_ladder im2022

Writes ``result/mm_ladder/<window>.json`` and ``result/mm_ladder/<window>.md``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import pandas as pd

from proto_market_maker.experiments import mm_anchor as A
from proto_market_maker.experiments.windows import WINDOWS, traded_contracts
from proto_market_maker.naive_variants import (CLOSE_TO, QUOTE_FROM, NaiveOptions,
                                               NaiveVariant)

RUNG_LABELS = {
    0: "naive as-is",
    1: "+ aligned (flat each session, 09:00-14:25, own-contract prints)",
    2: "+ own-price fills",
    3: "+ dated VSD IM (13% / 17%)",
    4: "+ fee on every fill",
    5: "faithful, optimistic queue",
    6: "faithful, conservative queue",
    7: "post-cutover sessions (regime guard)",
}


def _dec(x) -> Decimal:
    return Decimal(str(round(float(x), 10)))


def build_sessions(window: str, days: List[date], fcc):
    band, l2 = A._roots(window)
    traded = traded_contracts(days, fcc)
    matched = pd.read_parquet(Path(l2) / "local_quote_matched.parquet")
    matched = matched.sort_values("datetime", kind="stable")
    matched["day"] = matched["datetime"].dt.date
    t = matched["datetime"].dt.time
    matched = matched[(t >= QUOTE_FROM) & (t <= CLOSE_TO)]
    closes = pd.read_parquet(Path(band) / "quote_close.parquet")
    close_of = {(pd.Timestamp(d).date(), tk): _dec(p)
                for d, tk, p in zip(closes["datetime"], closes["tickersymbol"], closes["price"])}
    out = []
    for d in days:
        tk = traded[d]
        sub = matched[(matched["day"] == d) & (matched["tickersymbol"] == tk)]
        ticks = [(ts.to_pydatetime(), _dec(p)) for ts, p in zip(sub["datetime"], sub["price"])]
        out.append((d, tk, ticks, close_of.get((d, tk))))
    return out


def run_rung(n: int, window: str, days: List[date], fcc, step: Decimal, sessions=None) -> dict:
    if n == 0:
        r = A.run_naive(window, days, fcc, step)
        return {k: r[k] for k in ("hpr", "sharpe", "mdd", "end_equity_dong", "fills",
                                  "round_trips", "forced_reductions", "sessions",
                                  "end_inventory")}
    bt = NaiveVariant(Decimal("5e5"), NaiveOptions.rung(n))
    bt.run_sessions(sessions, step)
    equity = [float(a) * A.NAIVE_SCALE for a in bt.daily_assets]
    out = A._metrics(equity)
    out.update({
        "fills": bt.fills,
        "round_trips": bt.closing_fills,
        "closeout_contracts": bt.closeout_contracts,
        "marked_contracts": bt.marked_contracts,
        "forced_reductions": bt.forced_reductions,
        "fees_dong": float(bt.fees_charged) * A.NAIVE_SCALE,
        "sessions": len(bt.daily_returns),
        "end_inventory": bt.inventory,
        "options": NaiveOptions.rung(n).__dict__,
    })
    out.pop("start_equity_dong", None)
    return out


def faithful_rung(arm: dict, days: List[date]) -> dict:
    """Faithful numbers restricted to ``days`` from the per-session records."""
    keep = {d.isoformat() for d in days}
    recs = [r for r in arm["per_session"] if r["date"] in keep]
    equity = [float(A.DEPOSIT_DONG)] + [r["end_equity_dong"] for r in recs]
    m = A._metrics(equity)
    others = [r for r in arm["per_session"] if r["date"] not in keep]
    if others:  # refused sessions must be flat, so whole-window == subset
        assert all("refused" in r and not r.get("fills") for r in others)
        assert abs(arm["hpr"] - m["hpr"]) < 1e-12 and arm["end_equity_dong"] == m["end_equity_dong"]
    fills = sum(r.get("fills", 0) for r in recs)
    marked = sum(r.get("closeout_marked_contracts", 0) for r in recs)
    assert (fills - marked) % 2 == 0, (fills, marked)
    acc = sum(r.get("submitted", 0) - r.get("rejected", 0) for r in recs)
    ind = sum(r.get("indeterminate_orders", 0) for r in recs)
    m.pop("start_equity_dong", None)
    m.update({"fills": fills, "round_trips": (fills - marked) // 2,
              "round_trips_note": "derived: (fills - closeout_marked_contracts) / 2",
              "closeout_fills": sum(r.get("closeout_fills", 0) for r in recs),
              "closeout_marked_contracts": marked,
              "charges_dong": sum(r.get("charges_dong", 0.0) for r in recs),
              "sessions": len(recs),
              "accepted_orders": acc, "undecided_orders": ind,
              "undecided_order_rate": (ind / acc) if acc else None,
              "queue": arm["queue"]})
    return m


def run_ladder(window: str, anchor_path: Optional[Path] = None, log=print) -> dict:
    fcc, all_days = A.load_contract_map(window)
    step = A.step_param()
    days = [d for d in all_days if d < A.KRX_CUTOVER] if window == "krx2025" else all_days
    sessions = build_sessions(window, days, fcc)

    rungs = []
    for n in range(5):
        r = run_rung(n, window, days, fcc, step, sessions)
        r.update({"rung": n, "label": RUNG_LABELS[n], "source": "naive engine (this run)"})
        rungs.append(r)
        log(f"rung {n}: fills={r['fills']} rt={r['round_trips']} hpr={r['hpr']:+.4%}")

    anchor_path = anchor_path or (A.REPO / "result" / "mm_anchor" / f"{window}.json")
    raw = anchor_path.read_bytes()
    anchor = json.loads(raw)
    src = f"result/mm_anchor/{window}.json (read, not re-run)"
    opt = faithful_rung(anchor["faithful_by_queue"]["optimistic"], days)
    cons = faithful_rung(anchor["faithful"], days)
    for n, r in ((5, opt), (6, cons)):
        r.update({"rung": n, "label": RUNG_LABELS[n], "source": src})
        rungs.append(r)

    prev = None
    for r in rungs:
        r["delta_fills"] = None if prev is None else r["fills"] - prev["fills"]
        r["delta_round_trips"] = None if prev is None else r["round_trips"] - prev["round_trips"]
        r["delta_hpr"] = None if prev is None else r["hpr"] - prev["hpr"]
        prev = r

    rung7 = None
    if window == "krx2025":
        post = [d.isoformat() for d in all_days if d >= A.KRX_CUTOVER]
        recs = [r for r in anchor["faithful"]["per_session"] if r["date"] in post]
        diag = anchor.get("post_cutover_unguarded_diagnostic") or {}
        rung7 = {"rung": 7, "label": RUNG_LABELS[7], "source": src,
                 "sessions": len(recs),
                 "refused_sessions": sum(1 for r in recs if "refused" in r),
                 "refusal_reason": sorted({r.get("refused", "") for r in recs}),
                 "fills": sum(r.get("fills", 0) for r in recs),
                 "unguarded_diagnostic": {q: {"fills": a["fills"], "hpr": a["hpr"],
                                              "undecided_order_rate": a["indeterminate"]["order_rate"]}
                                          for q, a in diag.items()},
                 "naive_post_cutover_context": "naive 40-session HPR {:+.2%} vs 20 pre-cutover {:+.2%}".format(
                     anchor["naive"]["hpr"], anchor["naive_pre_cutover_only"]["hpr"])}

    return {
        "window": window,
        "sessions": [d.isoformat() for d in days],
        "session_set": "20 pre-cutover sessions" if window == "krx2025" else "all 40 sessions",
        "step": str(step),
        "units": "real dong (naive thousand-dong x 1000)",
        "rungs": rungs,
        "rung7": rung7,
        "anchor": {"path": f"result/mm_anchor/{window}.json",
                   "sha256": hashlib.sha256(raw).hexdigest(),
                   "plutus_simulator_commit": anchor.get("plutus_simulator_commit"),
                   "plutus_simulator_src_dirty": anchor.get("plutus_simulator_src_dirty"),
                   "faithful_rerun": False},
        "plutus_simulator_head_at_ladder_run": A._engine_commit(),
    }


def _pct(x):
    return "" if x is None else f"{x * 100:+.2f}%"


def _pp(x):
    return "" if x is None else f"{x * 100:+.2f} pp"


def _int(x):
    return "" if x is None else f"{x:+d}"


def markdown(out: dict) -> str:
    lines = [f"### {out['window']} ({out['session_set']})", "",
             "| rung | | fills | Δ fills | round trips | HPR | Δ HPR | undecided |",
             "|--:|---|--:|--:|--:|--:|--:|--:|"]
    for r in out["rungs"]:
        und = r.get("undecided_order_rate")
        lines.append(f"| {r['rung']} | {r['label']} | {r['fills']} | {_int(r['delta_fills'])} | "
                     f"{r['round_trips']} | {_pct(r['hpr'])} | {_pp(r['delta_hpr'])} | "
                     f"{'' if und is None else f'{und:.2%}'} |")
    r7 = out.get("rung7")
    if r7:
        lines.append(f"| 7 | {r7['label']} | {r7['fills']} | | | refused {r7['refused_sessions']}/"
                     f"{r7['sessions']} sessions | | |")
    a = out["anchor"]
    lines += ["", f"Rungs 5–6 (and 7) read from `{a['path']}` (sha256 `{a['sha256'][:16]}…`, "
              f"plutus-simulator `{a['plutus_simulator_commit'][:7]}`); not re-run."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("window", choices=sorted(WINDOWS))
    ap.add_argument("--anchor", type=Path, default=None,
                    help="mm_anchor JSON to read rungs 5-7 from (default result/mm_anchor/<window>.json)")
    args = ap.parse_args(argv)
    out = run_ladder(args.window, args.anchor)
    d = A.REPO / "result" / "mm_ladder"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{args.window}.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    md = markdown(out)
    (d / f"{args.window}.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
