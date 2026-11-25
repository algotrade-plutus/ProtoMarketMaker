"""MarketMaker attribution ladder, algorithm A fixed (RIVF'26 camera-ready).

Owner framing: the naive engine's behaviour **is** the algorithm A under study;
the naive engine (N) and Plutus (F) are environments. Every rung keeps A fixed
(same rows, same ``quote(price, inventory, 3.1)``, same 15 s / on-fill requote,
overnight carry, the same F1->F2 roll) and changes one environment rule:

======  ===============================================================
rung    environment
======  ===============================================================
N0      naive engine as-is
N1      + own-price fills (a crossed quote books at the bid/ask, not the print)
N2      + dated VSD IM (13% before 2022-12-15, 17% from it)
N3      + fee on every fill (opening fills too)
F-opt   Plutus, faithful-A, optimistic queue  (``mm_faithful_a``)
F-con   Plutus, faithful-A, conservative queue (``mm_faithful_a``)
======  ===============================================================

N0-N3 run here (``naive_variants``; pure, no plutus). F-opt / F-con are read
from ``result/mm_faithful_a/<window>_<queue>.json`` (sha256 recorded). Every
rung runs over the **whole window** (40 sessions; ``rungs``). Since
plutus-simulator ``391e2e2`` the post-KRX margin is modelled in both QD 26
layers, so krx2025's post-cutover sessions are no longer set apart as
unmodelled. krx2025 also carries two sub-window ``views`` cut from the same
runs: ``pre_cutover``, the 20 sessions before 2025-05-05 (the like-for-like
view of the results committed before ``391e2e2``, which compared those
sessions only; the naive rungs' pre-cutover span is checked equal to a
naive run on those sessions alone), and ``post_cutover``, the 20 sessions
from it, returns measured from the equity at the last pre-cutover close. A
carries inventory, so every cut marks the open position at that close,
exactly as N marks its own.

Units: real dong (naive thousand-dong x 1000), as ``mm_anchor``.

Run (after the four ``mm_faithful_a`` runs)::

    .venv/bin/python -m proto_market_maker.experiments.mm_ladder im2022
    .venv/bin/python -m proto_market_maker.experiments.mm_ladder krx2025

Writes ``result/mm_ladder/<window>.json`` and ``.md``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from decimal import Decimal
from collections import Counter
from typing import List, Optional

from proto_market_maker.experiments import mm_anchor as A
from proto_market_maker.experiments.windows import WINDOWS
from proto_market_maker.naive_variants import NaiveOptions, NaiveVariant

LABELS = {
    "N0": "naive as-is",
    "N1": "+ own-price fills",
    "N2": "+ dated VSD IM (13% / 17%)",
    "N3": "+ fee on every fill",
    "F-opt": "Plutus faithful-A, optimistic queue",
    "F-con": "Plutus faithful-A, conservative queue",
}
FA_DIR = A.REPO / "result" / "mm_faithful_a"


class _DailyCounts(NaiveVariant):
    """Records cumulative fills / round trips at each session end."""

    def update_pnl(self, close_price):
        super().update_pnl(close_price)
        self.daily_counts = getattr(self, "daily_counts", []) + [(self.fills, self.closing_fills)]


def naive_rung(n: int, data, step: Decimal) -> dict:
    bt = _DailyCounts(Decimal("5e5"), NaiveOptions.rung(n))
    bt.run(data.copy(), step)
    equity = [float(a) * A.NAIVE_SCALE for a in bt.daily_assets]
    days = [d.isoformat() for d in bt.tracking_dates]
    out = A._metrics(equity)
    out.pop("start_equity_dong", None)
    out.update({"fills": bt.fills, "round_trips": bt.closing_fills,
                "forced_reductions": bt.forced_reductions,
                "quote_fill_fees_dong": float(bt.fees_charged) * A.NAIVE_SCALE,
                "sessions": len(bt.daily_returns), "end_inventory": bt.inventory,
                "options": NaiveOptions.rung(n).__dict__,
                "_daily": {d: {"equity": e, "fills": f, "round_trips": r}
                           for d, e, (f, r) in zip(days, equity[1:], bt.daily_counts)}})
    return out


def naive_span(r: dict, days: List[str], base_day: Optional[str] = None) -> dict:
    """A sub-window of a whole-window naive rung: equity, fills and round trips
    from its per-session record, measured from ``base_day``'s close (or the
    deposit)."""
    daily = r["_daily"]
    base = daily[base_day] if base_day else {"equity": float(A.DEPOSIT_DONG), "fills": 0,
                                             "round_trips": 0}
    equity = [base["equity"]] + [daily[d]["equity"] for d in days]
    m = A._metrics(equity)
    m.pop("start_equity_dong", None)
    m.update({"fills": daily[days[-1]]["fills"] - base["fills"],
              "round_trips": daily[days[-1]]["round_trips"] - base["round_trips"],
              "sessions": len(days),
              "_daily": {d: {"equity": daily[d]["equity"], "fills": daily[d]["fills"] - base["fills"],
                             "round_trips": daily[d]["round_trips"] - base["round_trips"]}
                         for d in days}})
    return m


def first_roll(fa: dict, incomplete_only: bool):
    """First session with a non-empty roll (optionally: one that did not complete)."""
    for r in fa["per_session"]:
        if r.get("roll_contracts") and (not incomplete_only
                                        or r.get("roll_fills", 0) < 2 * r["roll_contracts"]):
            return r["date"]
    return None


def _sum(recs, key):
    return sum(r.get(key, 0) for r in recs)


def faithful_span(fa: dict, days: List[str], base_day: Optional[str] = None) -> dict:
    keep = set(days)
    recs = [r for r in fa["per_session"] if r["date"] in keep]
    assert [r["date"] for r in recs] == days, "faithful-A sessions differ from the naive rows"
    base = (float(A.DEPOSIT_DONG) if base_day is None else
            [r for r in fa["per_session"] if r["date"] == base_day][0]["end_equity_dong"])
    equity = [base] + [r["end_equity_dong"] for r in recs]
    m = A._metrics(equity)
    m.pop("start_equity_dong", None)
    accepted = sum(r.get(f"{role}_submitted", 0) - r.get(f"{role}_rejected", 0)
                   for r in recs for role in ("quote", "roll"))
    ind = _sum(recs, "indeterminate_orders")
    acc = [0, 0]
    daily = {}
    for r, e in zip(recs, equity[1:]):
        acc[0] += r.get("fills", 0); acc[1] += r.get("closing_fills", 0)
        daily[r["date"]] = {"equity": e, "fills": acc[0], "round_trips": acc[1]}
    m.update({
        "_daily": daily,
        "fills": _sum(recs, "fills"),
        "round_trips": _sum(recs, "closing_fills"),
        "quote_fills": _sum(recs, "quote_fills"),
        "roll_fills": _sum(recs, "roll_fills"),
        "engine_fills": _sum(recs, "engine_fills"),
        "maker_fills": _sum(recs, "maker_fills"),
        "taker_fills": _sum(recs, "taker_fills"),
        "sessions": len(recs),
        "accepted_orders": accepted,
        "undecided_orders": ind,
        "undecided_order_rate": (ind / accepted) if accepted else None,
        "undecided_quote_orders_in_atc": _sum(recs, "indeterminate_orders_atc"),
        "margin_warnings": _sum(recs, "margin_warning"),
        "margin_calls": _sum(recs, "margin_call"),
        "margin_calls_cleared": _sum(recs, "margin_call_cleared"),
        "forced_liquidations": _sum(recs, "forced_liquidation"),
        "forced_liquidations_executed": _sum(recs, "forced_liquidation_executed"),
        "vm_settlement_days": sum(1 for r in recs if r.get("positions")),
        "roll_triggers": _sum(recs, "roll_triggers"),
        "roll_contracts": _sum(recs, "roll_contracts"),
        "roll_retries": _sum(recs, "roll_retries"),
        "roll_rejected": _sum(recs, "roll_rejected"),
        "roll_unfilled_contracts": _sum(recs, "roll_unfilled_contracts"),
        "expiry_settled_contracts": _sum(recs, "expiry_settled_contracts"),
        "cancel_refused": _sum(recs, "cancel_refused"),
        "quote_rejected": _sum(recs, "quote_rejected"),
        "charges_dong": sum(r.get("charges_dong", 0.0) for r in recs),
        "end_net_contracts": recs[-1]["end_net"] if recs else None,
        "end_positions": recs[-1]["positions"] if recs else None,
        "engine_deposit_end_dong": recs[-1]["engine_deposit_dong"] if recs else None,
        "ledger_minus_engine_deposit_end_dong": (recs[-1]["end_equity_dong"]
                                                 - recs[-1]["engine_deposit_dong"]) if recs else None,
        "max_abs_deposit_drift_dong": max((abs(r["end_equity_dong"] - r["engine_deposit_dong"])
                                           for r in recs), default=None),
        "positions_match_engine_all_sessions": all(r["positions_match_engine"] for r in recs),
        # post-KRX VSDC CCP layer (plutus-simulator 391e2e2): closes with a position
        # after 2025-05-05, those it could not determine, why, and Dieu 13 states.
        "ccp_nights": _sum(recs, "ccp_nights"),
        "ccp_indeterminate_nights": _sum(recs, "ccp_indeterminate_nights"),
        "ccp_calendar_spread_unknown": _sum(recs, "ccp_calendar_spread_unknown"),
        "ccp_events_by_state": dict(Counter(
            e["state"] for e in fa.get("ccp_events", []) if e["on"] in keep)),
    })
    reasons = Counter()
    for r in recs:
        for k, v in r.items():
            if k.startswith("ccp_gap:"):
                reasons[k.split(":", 1)[1]] += v
    m["ccp_indeterminate_by_reason"] = dict(sorted(reasons.items()))
    return m


def _end_equity(fa: dict, day: str) -> float:
    return [r for r in fa["per_session"] if r["date"] == day][0]["end_equity_dong"]


def _deltas(rungs: List[dict]) -> None:
    prev = None
    for r in rungs:
        for k in ("fills", "round_trips", "hpr"):
            r[f"delta_{k}"] = None if prev is None else r[k] - prev[k]
        prev = r


def run_ladder(window: str, log=print) -> dict:
    from proto_market_maker.experiments.mm_faithful_a import naive_rows
    fcc, all_days = A.load_contract_map(window)
    step = A.step_param()
    data = naive_rows(window, all_days, fcc)
    days = [d.isoformat() for d in data["date"].unique().tolist()]
    pre_days = [d for d in days if d < A.KRX_CUTOVER.isoformat()]
    post_days = [d for d in days if d >= A.KRX_CUTOVER.isoformat()]
    split = window == "krx2025" and pre_days and post_days

    naive = []
    for n in range(4):
        r = naive_rung(n, data, step)
        r.update({"rung": f"N{n}", "label": LABELS[f"N{n}"], "source": "naive engine (this run)"})
        naive.append(r)
        log(f"N{n}: fills={r['fills']} rt={r['round_trips']} hpr={r['hpr']:+.4%}")

    # The pre-cutover view is cut from the whole-window naive run. Check that cut
    # equals a naive run on the pre-cutover sessions alone (the committed view).
    pre_only_check = None
    if split:
        pre_data = naive_rows(window, [d for d in all_days if d < A.KRX_CUTOVER], fcc)
        pre_only_check = {}
        for n, r in enumerate(naive):
            alone = naive_rung(n, pre_data, step)
            cut = naive_span(r, pre_days)
            pre_only_check[f"N{n}"] = (abs(alone["hpr"] - cut["hpr"]) < 1e-12
                                       and alone["fills"] == cut["fills"]
                                       and alone["round_trips"] == cut["round_trips"])

    sources, fas = {}, {}
    for key, q in (("F-opt", "optimistic"), ("F-con", "conservative")):
        path = FA_DIR / f"{window}_{q}.json"
        raw = path.read_bytes()
        fa = json.loads(raw)
        fas[key] = fa
        sources[key] = {"path": str(path.relative_to(A.REPO)),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "plutus_simulator_commit": fa["plutus_simulator_commit"],
                        "plutus_simulator_src_dirty": fa["plutus_simulator_src_dirty"],
                        "plutus_simulator_commit_at_end": fa.get("plutus_simulator_commit_at_end"),
                        "vm_settlements_whole_run": fa["vm_settlements"],
                        "engine_ignorance_whole_run": fa["engine_ignorance"],
                        "refusals_whole_run": fa["refusals"],
                        "ccp_events_whole_run": fa.get("ccp_events", []),
                        "ccp_state_end": fa.get("ccp_state_end"),
                        "wall_seconds": fa.get("wall_seconds")}

    def faithful_rungs(span, base_day=None):
        out = []
        for key in ("F-opt", "F-con"):
            r = faithful_span(fas[key], span, base_day)
            r.update({"rung": key, "label": LABELS[key], "source": sources[key]["path"]})
            out.append(r)
        return out

    rungs = naive + faithful_rungs(days)
    _deltas(rungs)

    views = None
    if split:
        views = {}
        for name, span, base, label in (
                ("pre_cutover", pre_days, None,
                 f"{len(pre_days)} pre-cutover sessions (like-for-like with the results committed "
                 "before plutus-simulator 391e2e2, which compared these sessions only)"),
                ("post_cutover", post_days, pre_days[-1],
                 f"{len(post_days)} post-cutover sessions from 2025-05-05 (QD 26 two-layer margin; "
                 f"returns from the {pre_days[-1]} close)")):
            vr = []
            for r in naive:
                x = naive_span(r, span, base)
                x.update({k: r[k] for k in ("rung", "label")})
                x["source"] = "naive engine (this run), cut from the whole window"
                vr.append(x)
            vr += faithful_rungs(span, base)
            _deltas(vr)
            views[name] = {"session_set": label, "sessions": span, "base_day": base, "rungs": vr}
        views["pre_cutover"]["naive_cut_equals_pre_only_run"] = pre_only_check

    # Cross-check checkpoint: every rung cut at the last session before the
    # first roll that did not complete in either queue or, if every roll
    # completed, before the first non-empty roll. It is free of anything the
    # roll does, so it shows whether the full-window direction is a roll artefact.
    refused = sorted(filter(None, (first_roll(fa, True) for fa in fas.values())))
    basis = "first roll that did not complete"
    if not refused:
        refused = sorted(filter(None, (first_roll(fa, False) for fa in fas.values())))
        basis = "first non-empty roll (every roll completed)"
    checkpoint = None
    if refused:
        before = [d for d in days if d < refused[0]]
        if before:
            cut = before[-1]
            rows, prev = [], None
            for r in rungs:
                x = r["_daily"][cut]
                hpr = x["equity"] / float(A.DEPOSIT_DONG) - 1.0
                rows.append({"rung": r["rung"], "fills": x["fills"], "round_trips": x["round_trips"],
                             "hpr": hpr, "delta_hpr": None if prev is None else hpr - prev,
                             "delta_fills": None if prev is None else x["fills"] - prows[-1]["fills"]})
                prev, prows = hpr, rows
            checkpoint = {"first_refused_roll_day": refused[0], "basis": basis, "through": cut,
                          "sessions": len(before), "rungs": rows}

    anchor = {}
    p = A.REPO / "result" / "mm_anchor" / f"{window}.json"
    if p.exists():
        a = json.loads(p.read_bytes())

        def same(ref, r):
            return abs(ref["hpr"] - r["hpr"]) < 1e-12 and ref["fills"] == r["fills"]
        anchor = {"naive_hpr": a["naive"]["hpr"], "naive_fills": a["naive"]["fills"],
                  "n0_matches_mm_anchor_naive": same(a["naive"], rungs[0]),
                  "mm_anchor_faithful_conservative_hpr_flat_each_session": a["faithful"]["hpr"],
                  "mm_anchor_faithful_optimistic_hpr_flat_each_session":
                      a["faithful_by_queue"]["optimistic"]["hpr"],
                  "mm_anchor_plutus_simulator_commit": a.get("plutus_simulator_commit")}
        if views and a.get("naive_pre_cutover_only"):
            ref = a["naive_pre_cutover_only"]
            anchor["pre_cutover_n0_matches_mm_anchor_naive_pre_cutover_only"] = same(
                ref, views["pre_cutover"]["rungs"][0])

    return {"window": window, "sessions": days,
            "session_set": f"all {len(days)} sessions",
            "step": str(step), "units": "real dong (naive thousand-dong x 1000)",
            "rungs": rungs, "views": views, "clean_checkpoint": checkpoint,
            "faithful_sources": sources, "mm_anchor_crosscheck": anchor,
            "plutus_simulator_head_at_ladder_run": A._engine_commit()}


def _pct(x):
    return "" if x is None else f"{x * 100:+.2f}%"


def _pp(x):
    return "" if x is None else f"{x * 100:+.2f} pp"


def _int(x):
    return "" if x is None else f"{x:+d}"


def _table(title: str, rungs: List[dict]) -> List[str]:
    lines = [title, "",
             "| rung | environment | fills | Δ fills | round trips | HPR | Δ HPR | undecided orders |",
             "|---|---|--:|--:|--:|--:|--:|--:|"]
    for r in rungs:
        und = r.get("undecided_order_rate")
        lines.append(f"| {r['rung']} | {r['label']} | {r['fills']} | {_int(r['delta_fills'])} | "
                     f"{r['round_trips']} | {_pct(r['hpr'])} | {_pp(r['delta_hpr'])} | "
                     f"{'' if und is None else f'{und:.2%}'} |")
    return lines


def _ccp_line(r: dict) -> str:
    why = ", ".join(f"{k} {v}" for k, v in r.get("ccp_indeterminate_by_reason", {}).items()) or "none"
    states = ", ".join(f"{k} {v}" for k, v in r.get("ccp_events_by_state", {}).items()) or "none"
    return (f"- {r['rung']}: CCP nights with a position {r.get('ccp_nights', 0)}, indeterminate "
            f"{r.get('ccp_indeterminate_nights', 0)} (reasons: {why}); calendar-spread UNKNOWN "
            f"{r.get('ccp_calendar_spread_unknown', 0)}; Dieu 13 transitions by new state: {states}")


def markdown(out: dict) -> str:
    lines = _table(f"### {out['window']} ({out['session_set']})", out["rungs"])
    c = out.get("clean_checkpoint")
    if c:
        lines += ["", f"Cross-check checkpoint: through {c['through']} ({c['sessions']} sessions), the last "
                      f"session before the {c['basis']} ({c['first_refused_roll_day']}):", "",
                  "| rung | fills | Δ fills | round trips | HPR | Δ HPR |", "|---|--:|--:|--:|--:|--:|"]
        for r in c["rungs"]:
            lines.append(f"| {r['rung']} | {r['fills']} | {_int(r['delta_fills'])} | {r['round_trips']} | "
                         f"{_pct(r['hpr'])} | {_pp(r['delta_hpr'])} |")
    f = [r for r in out["rungs"] if r["rung"].startswith("F")]
    lines += ["", "Faithful-A Tier-1 (same span):", "",
              "| | margin warnings | margin calls | forced liq. (executed) | VM settlement days | "
              "roll fills / roll legs | roll retries | roll unfilled | engine (forced) fills | "
              "max abs(ledger − engine deposit) |",
              "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for r in f:
        lines.append(f"| {r['rung']} | {r['margin_warnings']} | {r['margin_calls']} | "
                     f"{r['forced_liquidations']} ({r['forced_liquidations_executed']}) | "
                     f"{r['vm_settlement_days']} | {r['roll_fills']} / {2 * r['roll_contracts']} | "
                     f"{r['roll_retries']} | {r['roll_unfilled_contracts']} | "
                     f"{r['engine_fills']} | {r['max_abs_deposit_drift_dong']:,.0f}đ |")
    lines += ["", "Post-KRX VSDC CCP layer (whole window):", ""] + [_ccp_line(r) for r in f]
    for name, v in (out.get("views") or {}).items():
        lines += [""] + _table(f"#### {out['window']} view `{name}`: {v['session_set']}", v["rungs"])
        if name == "pre_cutover":
            chk = v.get("naive_cut_equals_pre_only_run") or {}
            lines += ["", "Naive pre-cutover cut equals a naive run on those sessions alone: "
                      + ", ".join(f"{k} {'yes' if ok else 'NO'}" for k, ok in chk.items()) + "."]
        if name == "post_cutover":
            lines += [""] + [_ccp_line(r) for r in v["rungs"] if r["rung"].startswith("F")]
    lines += [""]
    for k, s in out["faithful_sources"].items():
        end = s.get("plutus_simulator_commit_at_end")
        moved = f" (checkout moved to `{end[:7]}` before the run ended)" if end and end != s["plutus_simulator_commit"] else ""
        lines.append(f"{k}: `{s['path']}` sha256 `{s['sha256'][:16]}…`, plutus-simulator "
                     f"`{s['plutus_simulator_commit'][:7]}`{moved}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("window", choices=sorted(WINDOWS))
    args = ap.parse_args(argv)
    out = run_ladder(args.window)
    d = A.REPO / "result" / "mm_ladder"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{args.window}.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    md = markdown(out)
    (d / f"{args.window}.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
