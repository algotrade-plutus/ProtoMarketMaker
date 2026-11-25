"""Write ``result/REPORT.md``: the preliminary MarketMaker report (RIVF'26).

Owner principle: the repo keeps every experiment value faithfully and in full,
documented so it is easy to follow; the paper later picks a succinct subset.
Every number in the report is read from a result file at generation time
(``result/mm_ladder``, ``result/mm_faithful_a``, ``result/mm_anchor``,
``result/mm_markout``); the prose around them is fixed. Re-run after any
result changes::

    .venv/bin/python -m proto_market_maker.experiments.mm_report
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[3]
WINDOWS = ("im2022", "krx2025")
NAIVE = ("N0", "N1", "N2", "N3")
# Engine fixes on plutus-simulator rivf26 that may change faithful numbers
# (coordinator, 2026-11-25). The report checks which results include them.
ENGINE_FIXES = {
    "ba0d9f4": "band-edge orders on book sessions decided from the book, not the daily bar",
    "6e6c104": "soft policy: market-order fills graded like a limit at the band edge (evidence label)",
    "4867d46": "post-KRX margin modelled in QD 26's two layers (broker IM intraday, VSDC CCP after the close)",
}
RUNG_ADDS = {
    "N0": "the naive engine as-is: a quote fills when the last print crosses it and books at that print; "
          "flat 17% margin capacity; fee only on position-reducing fills",
    "N1": "own-price fills: a crossed quote books at its own bid/ask, not at the crossing print",
    "N2": "dated VSD initial margin for capacity: 13% before 2022-12-15, 17% from it",
    "N3": "the fee on every fill, opening fills too",
    "F-opt": "Plutus faithful-A, `book_walk` with the optimistic queue (A is first at its price level)",
    "F-con": "Plutus faithful-A, `book_walk` with the conservative queue (A is behind everything displayed)",
}


def _load(path: Path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _git(args: List[str], cwd: Path) -> Optional[str]:
    try:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def _sim_root() -> Path:
    from proto_market_maker.experiments import mm_anchor as A
    return A.SIM_ROOT


def includes_fix(result_commit: Optional[str], fix: str) -> str:
    if not result_commit or result_commit == "unknown":
        return "unknown"
    try:
        r = subprocess.run(["git", "-C", str(_sim_root()), "merge-base", "--is-ancestor", fix,
                            result_commit], capture_output=True)
    except Exception:
        return "unknown"
    return {0: "yes", 1: "no"}.get(r.returncode, "unknown")


def pct(x, nd=2):
    return "n/a" if x is None else f"{100 * x:+.{nd}f}%"


def pp(x):
    return "" if x is None else f"{100 * x:+.2f} pp"


def mdong(x):
    return "n/a" if x is None else f"{x / 1e6:+.1f}M đ"


def num(x, fmt="{:+.2f}"):
    return "n/a" if x is None else fmt.format(x)


def short(c):
    return (c or "unknown")[:7]


# ---------------------------------------------------------------------------

def gather(result: Path) -> dict:
    out = {"ladder": {}, "anchor": {}, "faithful": {}, "markout": []}
    for w in WINDOWS:
        p = result / "mm_ladder" / f"{w}.json"
        if p.exists():
            doc, sha = _load(p)
            out["ladder"][w] = {"doc": doc, "sha": sha, "path": f"result/mm_ladder/{w}.json"}
        p = result / "mm_anchor" / f"{w}.json"
        if p.exists():
            doc, sha = _load(p)
            out["anchor"][w] = {"doc": doc, "sha": sha, "path": f"result/mm_anchor/{w}.json"}
        for q in ("optimistic", "conservative"):
            p = result / "mm_faithful_a" / f"{w}_{q}.json"
            if p.exists():
                doc, sha = _load(p)
                out["faithful"][(w, q)] = {"doc": doc, "sha": sha,
                                           "path": f"result/mm_faithful_a/{w}_{q}.json"}
    d = result / "mm_markout"
    for p in sorted(d.glob("*_markout.json")) if d.exists() else []:
        doc, sha = _load(p)
        out["markout"].append({"doc": doc, "sha": sha, "path": f"result/mm_markout/{p.name}"})
    return out


def _rungs(L):
    return {r["rung"]: r for r in L["rungs"]}


def _ladder_table(title: str, R: Dict[str, dict]) -> List[str]:
    lines = [title, "",
             "| rung | environment | fills | Δ fills | round trips | return (HPR) | Δ HPR | max drawdown | "
             "undecided orders |",
             "|---|---|--:|--:|--:|--:|--:|--:|--:|"]
    for k in (*NAIVE, "F-opt", "F-con"):
        r = R[k]
        und = r.get("undecided_order_rate")
        df = r.get("delta_fills")
        lines.append(f"| {k} | {r['label']} | {r['fills']} | {'' if df is None else f'{df:+d}'} | "
                     f"{r['round_trips']} | {pct(r['hpr'])} | {pp(r.get('delta_hpr'))} | "
                     f"{pct(r.get('mdd'))} | {'' if und is None else f'{und:.2%}'} |")
    lo, hi = sorted((R["F-con"]["hpr"], R["F-opt"]["hpr"]))
    outside = [k for k in NAIVE if not lo <= R[k]["hpr"] <= hi]
    allv = [R[k]["hpr"] for k in (*NAIVE, "F-opt", "F-con")]
    lines += ["", f"- Range across the six environments: {pct(min(allv))} .. {pct(max(allv))} "
                  f"({100 * (max(allv) - min(allv)):.2f} pp), with A unchanged.",
              f"- Faithful queue band: {pct(lo)} (F-con) .. {pct(hi)} (F-opt), width "
              f"{100 * (hi - lo):.2f} pp. Naive rungs outside it: {', '.join(outside) or 'none'}"
              + (" (above it: " + ", ".join(k for k in outside if R[k]['hpr'] > hi) + ")"
                 if any(R[k]['hpr'] > hi for k in outside) else "")
              + (" (below it: " + ", ".join(k for k in outside if R[k]['hpr'] < lo) + ")"
                 if any(R[k]['hpr'] < lo for k in outside) else "") + "."]
    return lines


def _tier1(R: Dict[str, dict]) -> List[str]:
    lines = ["| arm | maker / taker fills | quote / roll / engine fills | margin warnings | margin calls | "
             "forced liq. (executed) | VM settlement days | roll fills / legs | roll retries | "
             "ledger − engine deposit (max abs) | positions match engine | CCP nights / indeterminate | "
             "calendar-spread UNKNOWN |",
             "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for k in ("F-opt", "F-con"):
        r = R[k]
        lines.append(f"| {k} | {r['maker_fills']} / {r['taker_fills']} | {r['quote_fills']} / "
                     f"{r['roll_fills']} / {r['engine_fills']} | {r['margin_warnings']} | "
                     f"{r['margin_calls']} | {r['forced_liquidations']} "
                     f"({r['forced_liquidations_executed']}) | {r['vm_settlement_days']} | "
                     f"{r['roll_fills']} / {2 * r['roll_contracts']} | {r['roll_retries']} | "
                     f"{r['max_abs_deposit_drift_dong']:,.0f} đ | "
                     f"{'yes' if r['positions_match_engine_all_sessions'] else 'NO'} | "
                     f"{r.get('ccp_nights', 0)} / {r.get('ccp_indeterminate_nights', 0)} | "
                     f"{r.get('ccp_calendar_spread_unknown', 0)} |")
    return lines


def section_ladder(w: str, G: dict) -> List[str]:
    Lw = G["ladder"][w]
    L = Lw["doc"]
    R = _rungs(L)
    lines = _ladder_table(f"### {w} ({L['session_set']}: {L['sessions'][0]} .. {L['sessions'][-1]})", R)
    c = L.get("clean_checkpoint")
    if c:
        lines += ["", f"Cross-check before any roll: through {c['through']} ({c['sessions']} sessions; "
                      f"cut at the last session before the {c['basis']}, {c['first_refused_roll_day']}). "
                      "It shows whether the full-window ordering is a roll artefact.", "",
                  "| rung | fills | round trips | HPR | Δ HPR |", "|---|--:|--:|--:|--:|"]
        for r in c["rungs"]:
            lines.append(f"| {r['rung']} | {r['fills']} | {r['round_trips']} | {pct(r['hpr'])} | "
                         f"{pp(r['delta_hpr'])} |")
    lines += ["", "Faithful-A Tier-1 counters (same span):", ""] + _tier1(R)
    for name, v in (L.get("views") or {}).items():
        VR = {r["rung"]: r for r in v["rungs"]}
        lines += [""] + _ladder_table(f"#### {w}, view `{name}`: {v['session_set']}", VR)
        if name == "pre_cutover":
            chk = v.get("naive_cut_equals_pre_only_run") or {}
            lines += [f"- The naive rungs' pre-cutover cut equals a naive run on those sessions alone: "
                      + ", ".join(f"{k} {'yes' if ok else 'NO'}" for k, ok in chk.items()) + "."]
        lines += ["", f"Faithful-A Tier-1 counters ({name}):", ""] + _tier1(VR)
    for k, src in L["faithful_sources"].items():
        ev = src.get("ccp_events_whole_run") or []
        if ev:
            lines += ["", f"QD 26 Điều 13 CCP transitions, {k} (reported by the engine, not enforced): "
                      + "; ".join(f"{e['on']} {e['checkpoint']} {e['previous_state']} → {e['state']} "
                                  f"(shortfall {e['shortfall_dong'] / 1e6:.1f}M đ)" for e in ev) + "."]
    x = L.get("mm_anchor_crosscheck") or {}
    if x:
        lines += ["", f"N0 equals the `mm_anchor` naive arm (HPR and fills): "
                      f"{'yes' if x.get('n0_matches_mm_anchor_naive') else 'NO'}."]
        if "pre_cutover_n0_matches_mm_anchor_naive_pre_cutover_only" in x:
            lines += [f"Pre-cutover N0 equals `mm_anchor`'s `naive_pre_cutover_only`: "
                      f"{'yes' if x['pre_cutover_n0_matches_mm_anchor_naive_pre_cutover_only'] else 'NO'}."]
    lines += ["", f"Source: `{Lw['path']}` (sha256 `{Lw['sha'][:16]}…`)."]
    return lines


def _full_markout(G, w) -> Optional[dict]:
    n_full = len(G["ladder"][w]["doc"]["sessions"]) if w in G["ladder"] else None
    best = None
    for m in G["markout"]:
        d = m["doc"]
        if d["window"] != w:
            continue
        if n_full is not None and len(d["sessions"]) == n_full and \
                all(a["sessions"] == n_full for a in d["arms"].values()):
            best = m
    return best


def _markout_table(title: str, arms: dict) -> List[str]:
    lines = [title, "",
             "| arm | sessions | contracts | taker share | taker price improvement, median (pt) | "
             "markout 1 min | 5 min | close | P&L | carry | mark switch | trading | mean abs end inventory |",
             "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for arm, a in arms.items():
        mm = a["markout_mean_points"]
        ts = a["taker_share"]
        lines.append(f"| {arm} | {a['sessions']} | {a['contracts']} | "
                     f"{'n/a' if ts is None else f'{ts:.0%}'} | "
                     f"{num(a['price_improvement_points']['median'])} | {num(mm['1m'])} | "
                     f"{num(mm['5m'])} | {num(mm['close'])} | {mdong(a['pnl_dong'])} | "
                     f"{mdong(a['carry_dong'])} | {mdong(a.get('mark_switch_dong', 0.0))} | "
                     f"{mdong(a['trading_dong'])} | "
                     f"{num(a.get('mean_abs_end_inventory'), '{:.1f}')} |")
    return lines


def section_markout(G: dict) -> List[str]:
    lines = []
    if not G["markout"]:
        lines += ["No markout result yet. **PENDING.**"]
    for m in G["markout"]:
        d = m["doc"]
        lines += [""] + _markout_table(f"#### {d['window']}: {d['session_set']} (price path: "
                                       f"{d['price_path']})", d["arms"])
        for name, v in (d.get("views") or {}).items():
            lines += [""] + _markout_table(f"##### {d['window']}, view `{name}`: {v['session_set']}",
                                           v["arms"])
        roles = "; ".join(f"{arm} " + ", ".join(f"{k} {v}" for k, v in a["by_role"].items())
                          for arm, a in d["arms"].items())
        lines += ["", f"Contracts by order role: {roles}. (Naive roll legs are its book-keeping roll at the "
                      "prints; the ladder's fill counts exclude them. Bare-list fill files carry no role: "
                      "`unknown`.)"]
        chk = {arm: a.get("fills_match_equity_source_per_session") for arm, a in d["arms"].items()}
        lines += [f"Fill contracts per session equal the equity source's own fill count: "
                  + ", ".join(f"{arm} {'yes' if v else ('n/a' if v is None else 'NO')}" for arm, v in chk.items())
                  + "."]
        lines += ["1-minute markouts: " + ", ".join(
            f"{arm} {num(a['markout_mean_points']['1m'])} ({'negative' if (a['markout_mean_points']['1m'] or 0) < 0 else 'not negative'})"
            for arm, a in d["arms"].items()) + "."]
        notes = [f"{arm}: {a['ticker_inferred']} fills carried no contract and were assigned one "
                 f"({a['ticker_ambiguous']} ambiguous)" for arm, a in d["arms"].items() if a["ticker_inferred"]]
        inputs = []
        for arm, p in d.get("inputs", {}).items():
            src = "naive trace run by `mm_markout`" if p.get("traced_here") else \
                f"`{p.get('fills_file')}` (sha256 `{p.get('fills_sha256', '')[:16]}…`)"
            if p.get("per_session_from"):
                src += f", equity from `{p['per_session_from']['path']}`"
            inputs.append(f"{arm}: {src}")
        lines += [""] + [f"- {n}." for n in notes] + [f"- Inputs: {'; '.join(inputs)}.",
                                                      f"- Source: `{m['path']}` (sha256 `{m['sha'][:16]}…`)."]
    for w in WINDOWS:
        if w in G["ladder"] and _full_markout(G, w) is None:
            lines += ["", f"**{w} full-window markouts: PENDING** (needs the full-window fill traces "
                          "of every arm; commands in the Reproduce section)."]
    return lines


def section_carry(G: dict, w: str = "im2022") -> List[str]:
    m = _full_markout(G, w)
    partial = [x for x in G["markout"] if x["doc"]["window"] == w]
    if m is None and not partial:
        return [f"**PENDING** (no {w} markout result yet)."]
    lines = []
    use = m or partial[-1]
    d = use["doc"]
    if m is None:
        lines += [f"**Full-window decomposition PENDING.** Partial values below ({d['session_set']}), "
                  "not the window result.", ""]
    lines += ["| arm | P&L | carry (overnight inventory × close-to-close move) | mark switch (naive F1/F2 "
              "stitch) | trading (the rest) | mean abs end inventory |", "|---|--:|--:|--:|--:|--:|"]
    for arm, a in d["arms"].items():
        lines.append(f"| {arm} | {mdong(a['pnl_dong'])} | {mdong(a['carry_dong'])} | "
                     f"{mdong(a.get('mark_switch_dong', 0.0))} | "
                     f"{mdong(a['trading_dong'])} | {num(a.get('mean_abs_end_inventory'), '{:.1f}')} |")
    miss = {arm: a["carry_missing_close"] for arm, a in d["arms"].items() if a["carry_missing_close"]}
    if miss:
        lines += ["", f"Carried positions with no close (no carry booked): {miss}."]
    lines = [f"#### {w} ({d['session_set']})", ""] + lines
    lines += ["", f"Source: `{use['path']}`."]
    return lines


def section_provenance(G: dict) -> List[str]:
    lines = ["| result | sha256 | plutus-simulator commit | at end of run | src dirty | "
             + " | ".join(f"includes {k}" for k in ENGINE_FIXES) + " |",
             "|---|---|---|---|---|" + "---|" * len(ENGINE_FIXES)]

    def row(path, sha, c, c_end, dirty):
        inc = " | ".join(includes_fix(c_end or c, k) for k in ENGINE_FIXES)
        lines.append(f"| `{path}` | `{sha[:12]}` | `{short(c)}` | `{short(c_end or c)}` | "
                     f"{'n/a' if dirty is None else ('yes' if dirty else 'no')} | {inc} |")
    for (w, q), f in sorted(G["faithful"].items()):
        d = f["doc"]
        row(f["path"], f["sha"], d.get("plutus_simulator_commit"), d.get("plutus_simulator_commit_at_end"),
            d.get("plutus_simulator_src_dirty"))
    for w, a in G["anchor"].items():
        d = a["doc"]
        row(a["path"], a["sha"], d.get("plutus_simulator_commit"), None, d.get("plutus_simulator_src_dirty"))
    for w, L in G["ladder"].items():
        row(L["path"], L["sha"], L["doc"].get("plutus_simulator_head_at_ladder_run"), None, None)
    for m in G["markout"]:
        c = m["doc"].get("plutus_simulator_head")
        lines.append(f"| `{m['path']}` | `{m['sha'][:12]}` | `{short(c)}` (head when assembled) | | n/a | "
                     + " | ".join("see faithful inputs" for _ in ENGINE_FIXES) + " |")
    lines += ["", "Engine fixes checked: " + "; ".join(f"`{k}` {v}" for k, v in ENGINE_FIXES.items())
              + ". \"no\" means the result predates the fix and the faithful numbers may move on a rerun. "
                "A ladder or markout row records the engine head when it was assembled; its faithful "
                "inputs carry their own commits (the `mm_faithful_a` rows). \"includes\" is judged on the "
                "commit at the end of the run."]
    return lines


def build(result: Path) -> str:
    G = gather(result)
    if not G["ladder"]:
        raise SystemExit("no result/mm_ladder/*.json")
    repo_head = _git(["rev-parse", "--short", "HEAD"], REPO) or "unknown"
    L = {w: _rungs(G["ladder"][w]["doc"]) for w in G["ladder"]}
    A = {w: G["anchor"][w]["doc"] for w in G["anchor"]}
    o = []
    o += ["# MarketMaker under naive and faithful execution: preliminary report (RIVF'26)", "",
          f"Generated by `proto_market_maker.experiments.mm_report` from the result files at repo commit "
          f"`{repo_head}` (branch `rivf26`). Every number below is read from a result file; regenerate "
          "rather than edit. Status: **preliminary**. Which engine fixes each result includes is in "
          "Provenance (section 9).", "",
          "Companion files: figure and tables in `result/paper_kit/` (README there); raw results in "
          "`result/mm_ladder/`, `result/mm_faithful_a/`, `result/mm_markout/`, `result/mm_anchor/`.", ""]
    o += ["## 1. The question", "",
          "Hold the algorithm fixed and change only the execution environment: how much of a market maker's "
          "backtest result is the algorithm, and how much is the simulator's fill assumptions?", "",
          "**Algorithm A** is this repo's naive engine *behaviour*: the merged F1/F2 rows the naive engine "
          "iterates; `quote(price, inventory, 3.1)` on the row price (inventory-skewed bid/ask about 3.1 points "
          "from the last print); requote every 15 s or right after a fill; one contract per side; inventory "
          "carried overnight; the naive F1→F2 roll on the session before expiry. **The naive engine (N) and "
          "Plutus (F) are environments.** Each ladder rung keeps A fixed and changes one environment rule.", ""]
    o += ["## 2. The environments", "", "| rung | what it adds |", "|---|---|"]
    o += [f"| {k} | {v} |" for k, v in RUNG_ADDS.items()]
    o += ["", "N0..N3 are cumulative opt-in options on `naive_variants.NaiveVariant` (`backtest.py` is unchanged). "
              "F-opt / F-con run A in one multi-day Plutus `ExchangeSession` (`experiments/mm_faithful_a.py`): "
              "the engine settles variation margin daily, applies the dated VSD IM, runs the margin ladder and "
              "executes forced closes; A's roll is sent as real orders; quotes resting at 14:30 meet the closing "
              "auction under the engine's rules; P&L is the harness ledger in real đồng (500,000,000 đ deposit, "
              "100,000 đ per index point), cross-checked against the engine deposit.", "",
          "Windows: `im2022`, 20 sessions either side of the 2022-12-15 VSD IM step (13% → 17%; book from the "
          "local archive), and `krx2025`, 20 sessions either side of the 2025-05-05 KRX cutover (book from the "
          "Algotrade DB). Every rung runs over all 40 sessions of its window: since plutus-simulator `4867d46` "
          "the post-KRX margin is modelled in QD 26's two layers (broker IM on VSDC's published 0.17 "
          "intraday, no VM; the VSDC CCP requirement after each close on the VN30 index close, which the "
          "krx2025 slice carries), so the post-cutover sessions are no longer set apart as unmodelled. "
          "krx2025 also shows two views cut from the same runs: `pre_cutover`, the 20 sessions before "
          "2025-05-05 (like for like with the results committed before `4867d46`, which compared those "
          "only), and `post_cutover`, the 20 from it. Slices and sha256: `data/<window>-MANIFEST.md`.", ""]
    o += ["## 3. Results: the ladder", ""]
    o += ["![MM ladder](paper_kit/mm_ladder.png)", "",
          "Figure: final return per environment; the shaded band is the faithful queue band F-con..F-opt "
          "(`result/paper_kit/mm_ladder.pdf`).", ""]
    for w in WINDOWS:
        if w in G["ladder"]:
            o += section_ladder(w, G) + [""]
    o += ["## 4. The queue band is a bound by construction", "",
          "The optimistic queue puts A first at its price level; the conservative queue puts A behind every "
          "contract displayed at that level. Every real queue position lies between the two for the given "
          "data, so the faithful result for the data is bracketed by [F-con, F-opt] rather than given as one "
          "number. Caveat: the conservative arm cannot decide quotes resting beyond the three observed book "
          "levels (section 7), which weakens that side of the band.", ""]
    for w in WINDOWS:
        if w not in L:
            continue
        spans = [(w, L[w])]
        for name, v in (G["ladder"][w]["doc"].get("views") or {}).items():
            spans.append((f"{w} `{name}`", {r["rung"]: r for r in v["rungs"]}))
        for lab, R in spans:
            lo, hi = sorted((R["F-con"]["hpr"], R["F-opt"]["hpr"]))
            up = [k for k in NAIVE if R[k]["hpr"] > hi]
            dn = [k for k in NAIVE if R[k]["hpr"] < lo]
            o.append(f"- {lab}: band {pct(lo)} .. {pct(hi)}; naive above it: {', '.join(up) or 'none'}; "
                     f"below it: {', '.join(dn) or 'none'}.")
    o += ["", "Naive can fall outside the band in either direction: the sign of its bias is not fixed.", ""]
    o += ["## 5. Why: adverse selection (markouts)", "",
          "Markout of a fill at horizon h, per contract, in index points, + = good for A: "
          "`price(t+h) − fill` for a buy, `fill − price(t+h)` for a sell; price(t+h) is the last print of the "
          "contract filled (shipped tape), `close` the official close. The naive touch-fill rule fills A "
          "when the market runs through its quote, so naive fills are adversely selected by construction; "
          "faithful fills include taker fills (a quote that crosses the book) at a price at or better than "
          "the limit. A ghost-fill check reads the 1-minute markouts: a simulator that filled quotes the "
          "tape would not reach would show fills the market immediately moves through. "
          "Code: `experiments/mm_fills_trace.py`, `experiments/mm_markout.py`.", "",
          "Note: an earlier throwaway analysis marked every fill against the F1 price. The first im2022 "
          "session (2022-11-17) is a roll day on which A quotes F2, so its numbers carried the F1/F2 basis on "
          "that day; the values here mark each fill against the contract filled and supersede it."]
    o += section_markout(G) + [""]
    o += ["## 6. Carry vs trading", "",
          "Daily P&L split into carry (the previous session's end positions × the close-to-close move of each "
          "contract held) and trading (everything else: intraday fills, fees, the roll). This separates what "
          "A earned by quoting from what its overnight inventory earned or lost. Naive keeps one stitched "
          "F1/F2 position and marks it to F2 on its roll session, to the expiring F1 on expiry day and to the "
          "new F1 after; the basis in those revaluations is shown apart as mark switch "
          "(P&L = carry + mark switch + trading).", ""]
    for w in WINDOWS:
        o += section_carry(G, w) + [""]
    o += ["## 7. Limits", ""]
    lim = ["**No real fills.** The Algotrade desk's fill or slippage statistics are not available (R3.1 closed). "
           "Credibility rests on the queue band as a bound, the tape markouts, exact accounting (ledger = engine "
           "deposit), complete rolls and dated margin; no arm is claimed to be the truth."]
    for w in WINDOWS:
        if w in L:
            r = L[w]["F-con"]
            lim.append(f"**Conservative queue undecided beyond the observed depth** ({w}): "
                       f"{r['undecided_order_rate']:.2%} of F-con's accepted orders were undecided at least once "
                       f"(F-opt: {L[w]['F-opt']['undecided_order_rate']:.2%}). A quotes about 31 ticks from the "
                       "last print, beyond the three book levels in the data, so the queue ahead is unobservable; "
                       "owner decision: stay undecided, the band carries the result.")
    if "krx2025" in L:
        Rk = L["krx2025"]
        Lk = G["ladder"]["krx2025"]["doc"]
        parts = []
        for k in ("F-opt", "F-con"):
            r = Rk[k]
            why = ", ".join(f"`{g}` {n}" for g, n in r.get("ccp_indeterminate_by_reason", {}).items()) or "none"
            ign = Lk["faithful_sources"][k]["engine_ignorance_whole_run"]["silent_ignorance"]
            uns = ign.get("rule.margin_model.unsourced", 0)
            parts.append(f"{k}: {r.get('ccp_nights', 0)} post-cutover closes with a position, "
                         f"{r.get('ccp_indeterminate_nights', 0)} indeterminate (reasons: {why}), "
                         f"{r.get('ccp_calendar_spread_unknown', 0)} calendar-spread UNKNOWN; "
                         f"`rule.margin_model.unsourced` {uns}")
        lim.append("**Post-KRX margin: QD 26's two layers, CCP layer reported, not enforced.** From 2025-05-05 "
                   "the broker layer margins intraday on VSDC's published IM (0.17, no VM) and the VSDC CCP "
                   "layer computes the binding requirement after each close on the VN30 index close; a "
                   "night it cannot compute is INDETERMINATE (a calendar spread held at the close needs the "
                   "unpublished SMrate). " + "; ".join(parts) + ". The engine reports QD 26 Điều 13's CCP "
                   "states (notified / suspended / closed out) but does not enforce them: a suspension does "
                   "not block A's opening orders. Margin assets are cash only.")
    stale = [f["path"] for f in G["faithful"].values()
             if any(includes_fix(f["doc"].get("plutus_simulator_commit_at_end")
                                 or f["doc"].get("plutus_simulator_commit"), k) != "yes"
                    for k in ENGINE_FIXES)]
    if stale:
        lim.append("**Some faithful results predate an engine fix listed under Provenance** ("
                   + ", ".join(f"`{x}`" for x in stale) + "); a rerun on the current engine may move them.")
    lim.append("**Sessions where the band has no ceiling/floor data** are recorded in `data/im2022-MANIFEST.md`.")
    o += [f"- {x}" for x in lim] + [""]
    if A:
        anchor_note = []
        for w, d in A.items():
            refused = d.get("faithful", {}).get("refused_sessions")
            if refused and includes_fix(d.get("plutus_simulator_commit"), "4867d46") != "yes":
                anchor_note.append(
                    f"The committed `{w}` anchor predates plutus-simulator `4867d46`: its regime guard "
                    f"refused {refused} post-cutover sessions as unsourced. The guard now accepts the sourced "
                    "`krx_two_layer` model and would quote them; the anchor has not been rerun.")
        o += ["## 8. Context: the earlier anchor (flat each session, regime guard on)", "",
              "`mm_anchor` runs a different faithful arm (closes out every session; its regime guard quotes "
              "only under a known dated margin model). Kept for the record; the ladder above is the A-fixed "
              "comparison.", ""] + ([" ".join(anchor_note), ""] if anchor_note else []) + [
              "| window | naive HPR (fills) | faithful conservative HPR (fills) | faithful optimistic HPR (fills) | "
              "conservative untaped HPR (fills) |", "|---|--:|--:|--:|--:|"]
        for w, d in A.items():
            fq = d["faithful_by_queue"]
            n = d["naive"]
            o.append(f"| {w} | {pct(n['hpr'])} ({n['fills']}) | {pct(d['faithful']['hpr'])} "
                     f"({d['faithful']['fills']}) | {pct(fq['optimistic']['hpr'])} ({fq['optimistic']['fills']}) | "
                     f"{pct(fq['conservative_untaped']['hpr'])} ({fq['conservative_untaped']['fills']}) |")
            if d.get("naive_pre_cutover_only"):
                p = d["naive_pre_cutover_only"]
                o.append(f"| {w} (naive, pre-cutover only) | {pct(p['hpr'])} ({p['fills']}) | | | |")
        o += [""]
    o += ["## 9. Provenance", ""] + section_provenance(G) + [""]
    o += ["## 10. Reproduce", "",
          "All commands run from the repo root with the repo's `.venv` (plutus-simulator installed editable "
          "from its `rivf26` checkout) and read only the shipped `data/` slices.", "", "```bash",
          "# faithful-A runs (one per window x queue; one progress line per session to --log;",
          "# --trace-out also writes the run's fill trace for the markouts)",
          "for W in im2022 krx2025; do",
          "  .venv/bin/python -m proto_market_maker.experiments.mm_faithful_a $W --queue optimistic \\",
          "    --log faithful_${W}_optimistic.log --trace-out result/mm_markout/${W}_fills_F-opt.json",
          "  .venv/bin/python -m proto_market_maker.experiments.mm_faithful_a $W --queue conservative \\",
          "    --log faithful_${W}_conservative.log --trace-out result/mm_markout/${W}_fills_F-con.json",
          "done",
          "# the ladder (naive rungs run here; faithful read from result/mm_faithful_a)",
          ".venv/bin/python -m proto_market_maker.experiments.mm_ladder im2022",
          ".venv/bin/python -m proto_market_maker.experiments.mm_ladder krx2025",
          "# fill traces (naive rungs; the faithful arms' traces come from --trace-out above, or",
          "# rerun them here: the same deterministic run; --log is required, one line per session)",
          "for W in im2022 krx2025; do for ARM in N0 N3 F-opt F-con; do",
          "  .venv/bin/python -m proto_market_maker.experiments.mm_fills_trace $W --arm $ARM --log trace_${W}_${ARM}.log",
          "done; done",
          "# markouts (reads result/mm_markout/<window>_fills_<arm>.json; --fills ARM=PATH for other files)",
          ".venv/bin/python -m proto_market_maker.experiments.mm_markout im2022",
          ".venv/bin/python -m proto_market_maker.experiments.mm_markout krx2025",
          "# figure and tables, then this report",
          ".venv/bin/python -m proto_market_maker.experiments.mm_paper_kit",
          ".venv/bin/python -m proto_market_maker.experiments.mm_report",
          ".venv/bin/python -m pytest -q", "```", ""]
    o += ["## 11. Draft paragraph (not paper text; for the owner's decision)", ""]
    if all(w in L for w in WINDOWS):
        rng = {w: (min(L[w][k]["hpr"] for k in L[w] if k in (*NAIVE, "F-opt", "F-con")),
                   max(L[w][k]["hpr"] for k in L[w] if k in (*NAIVE, "F-opt", "F-con"))) for w in WINDOWS}
        o += [f"> Holding a market-making algorithm fixed and changing only the execution environment moves its "
              f"return from {pct(rng['im2022'][1], 1)} to {pct(rng['im2022'][0], 1)} (im2022) and from "
              f"{pct(rng['krx2025'][1], 1)} to {pct(rng['krx2025'][0], 1)} (krx2025): for a "
              "market maker the fill model is the P&L. The naive touch-fill rule is not uniformly flattering: "
              "it fills the algorithm as the market runs through its quote, which tape markouts show as adverse "
              "selection. Plutus reports a band bounded by the optimistic and conservative queue positions, "
              "which brackets every queue position the data allows, and the naive result can fall outside it "
              "in either direction.", ""]
    return "\n".join(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--result", type=Path, default=REPO / "result")
    ap.add_argument("--out", type=Path, default=REPO / "result" / "REPORT.md")
    args = ap.parse_args(argv)
    args.out.write_text(build(args.result))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
