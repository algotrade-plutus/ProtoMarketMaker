"""Paper kit for the MarketMaker experiment (RIVF'26 camera-ready).

Reads the committed results and writes the figure and tables the paper uses.
Every number is read from a result file; nothing is typed in.

Inputs:

* ``result/mm_ladder/<window>.json`` (required, both windows): the ladder
  N0..N3 (naive environment, algorithm A fixed) and F-opt / F-con (Plutus
  faithful-A, optimistic / conservative queue).
* ``result/mm_markout/*_markout.json`` (optional): markouts, liquidity and
  carry/trading P&L per arm (``mm_markout``).

Outputs under ``result/paper_kit/``:

* ``mm_ladder.pdf`` / ``.png``: per window, the final return of each naive
  rung (dots) and the faithful queue band F-con..F-opt (shaded across the
  panel, so a naive rung outside it is visible). Column width 3.5 in,
  Okabe-Ito colours plus marker shape (colour is never the only cue).
* ``mm_ladder.tex`` / ``.md``: the ladder table.
* ``mm_markout.tex`` / ``.md``: the markout table (when markout results exist).
* ``kit.json``: every value used, with the sha256 of each source file.

Run::

    .venv/bin/python -m proto_market_maker.experiments.mm_paper_kit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[3]
WINDOW_ORDER = ("im2022", "krx2025")
NAIVE = ("N0", "N1", "N2", "N3")
ROW_LABEL = {"N0": "N0 naive", "N1": "N1 +own-price fill",
             "N2": "N2 +dated IM", "N3": "N3 +fee every fill",
             "F": "F Plutus (queue band)"}
# Okabe-Ito (colour-blind safe); identity also carried by marker / fill shape.
C_NAIVE = "#0072B2"
C_FAITH = "#D55E00"
INK = "#222222"
MUTED = "#666666"


def _read(path: Path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def load_ladder(result: Path) -> Dict[str, dict]:
    out = {}
    for w in WINDOW_ORDER:
        p = result / "mm_ladder" / f"{w}.json"
        if not p.exists():
            continue
        doc, sha = _read(p)
        rungs = {r["rung"]: r for r in doc["rungs"]}
        out[w] = {"source": str(p.relative_to(result.parent)), "sha256": sha,
                  "session_set": doc["session_set"], "sessions": len(doc["sessions"]),
                  "rungs": {k: {"hpr": rungs[k]["hpr"], "fills": rungs[k]["fills"],
                                "round_trips": rungs[k]["round_trips"],
                                "label": rungs[k]["label"]}
                            for k in (*NAIVE, "F-opt", "F-con")}}
        lo, hi = sorted((rungs["F-con"]["hpr"], rungs["F-opt"]["hpr"]))
        out[w]["band"] = {"low": lo, "high": hi}
        out[w]["naive_outside_band"] = [k for k in NAIVE
                                        if not lo <= rungs[k]["hpr"] <= hi]
    return out


def load_markouts(result: Path) -> List[dict]:
    rows = []
    d = result / "mm_markout"
    for p in sorted(d.glob("*_markout.json")) if d.exists() else []:
        doc, sha = _read(p)
        if ", first " in doc["session_set"]:
            continue                      # partial-window checks stay out of the paper kit
        rows.append({"source": str(p.relative_to(result.parent)), "sha256": sha,
                     "window": doc["window"], "session_set": doc["session_set"],
                     "price_path": doc["price_path"],
                     "arms": {k: {"sessions": a["sessions"], "contracts": a["contracts"],
                                  "taker_share": a["taker_share"],
                                  "price_improvement_median": a["price_improvement_points"]["median"],
                                  "markout_mean_points": a["markout_mean_points"],
                                  "pnl_dong": a["pnl_dong"], "carry_dong": a["carry_dong"],
                                  "mark_switch_dong": a.get("mark_switch_dong", 0.0),
                                  "trading_dong": a["trading_dong"]}
                              for k, a in doc["arms"].items()}})
    return rows


# ---------------------------------------------------------------------------
# figure
# ---------------------------------------------------------------------------

def figure(ladder: Dict[str, dict], out_stem: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7,
                         "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
                         "pdf.fonttype": 42, "ps.fonttype": 42,
                         "font.family": "DejaVu Sans", "axes.edgecolor": MUTED,
                         "axes.linewidth": 0.6, "xtick.color": MUTED, "ytick.color": INK})
    wins = [w for w in WINDOW_ORDER if w in ladder]
    vals = [100 * ladder[w]["rungs"][k]["hpr"] for w in wins for k in (*NAIVE, "F-opt", "F-con")]
    xmin, xmax = min(vals + [0.0]), max(vals + [0.0])
    span = xmax - xmin
    fig, axes = plt.subplots(len(wins), 1, figsize=(3.5, 1.35 * len(wins) + 0.45),
                             sharex=True, squeeze=False)
    rows = [*NAIVE, "F"]
    ys = {k: len(rows) - 1 - i for i, k in enumerate(rows)}
    for ax, w in zip(axes[:, 0], wins):
        L = ladder[w]
        r = L["rungs"]
        lo, hi = 100 * L["band"]["low"], 100 * L["band"]["high"]
        ax.axvspan(lo, hi, color=C_FAITH, alpha=0.12, lw=0, zorder=0)
        ax.axvline(0, color=MUTED, lw=0.5, zorder=1)
        # faithful band row: a bar from F-con to F-opt, end markers labelled
        y = ys["F"]
        ax.plot([lo, hi], [y, y], color=C_FAITH, lw=3.2, solid_capstyle="butt", zorder=2)
        for key, mk in (("F-con", "<"), ("F-opt", ">")):
            x = 100 * r[key]["hpr"]
            ax.plot([x], [y], marker="s", ms=3.6, color=C_FAITH, mec="white", mew=0.6, zorder=3)
            name = "con" if key == "F-con" else "opt"
            ax.annotate(f"{name} {x:+.1f}%", (x, y), xytext=(0, -4),
                        textcoords="offset points", va="top", ha="center",
                        fontsize=6, color=INK)
        # naive rungs: dots joined in ladder order
        xs = [100 * r[k]["hpr"] for k in NAIVE]
        ax.plot(xs, [ys[k] for k in NAIVE], color=C_NAIVE, lw=0.8, zorder=2)
        for k, x in zip(NAIVE, xs):
            ax.plot([x], [ys[k]], marker="o", ms=4, color=C_NAIVE, mec="white", mew=0.6, zorder=3)
            ax.annotate(f"{x:+.1f}%", (x, ys[k]), xytext=(4, 0), textcoords="offset points",
                        va="center", ha="left", fontsize=6, color=INK)
        ax.set_yticks([ys[k] for k in rows])
        ax.set_yticklabels([ROW_LABEL[k] for k in rows])
        ax.set_ylim(-1.0, len(rows) - 0.4)
        ax.set_title(f"{w}: {L['session_set']}", loc="left", pad=3)
        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", length=2, width=0.5)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.grid(axis="x", color="#dddddd", lw=0.4, zorder=0)
        ax.set_axisbelow(True)
    axes[-1, 0].set_xlim(xmin - 0.12 * span, xmax + 0.22 * span)
    axes[-1, 0].set_xlabel("final return of algorithm A over the window (%)")
    fig.tight_layout(h_pad=0.6)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_stem.with_suffix(".pdf"))
    fig.savefig(out_stem.with_suffix(".png"), dpi=300)
    plt.close(fig)


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------

def _pct(x):
    return f"{100 * x:+.2f}%"


def _tpct(x):
    return f"${100 * x:+.2f}$\\%"


def ladder_md(ladder: Dict[str, dict]) -> str:
    wins = [w for w in WINDOW_ORDER if w in ladder]
    head = "| rung | environment | " + " | ".join(
        f"{w} return | {w} fills" for w in wins) + " |"
    lines = [head, "|---|---|" + "--:|--:|" * len(wins)]
    for k in (*NAIVE, "F-opt", "F-con"):
        lab = ladder[wins[0]]["rungs"][k]["label"]
        cells = " | ".join(f"{_pct(ladder[w]['rungs'][k]['hpr'])} | {ladder[w]['rungs'][k]['fills']}"
                           for w in wins)
        lines.append(f"| {k} | {lab} | {cells} |")
    lines.append("")
    for w in wins:
        L = ladder[w]
        out = ", ".join(L["naive_outside_band"]) or "none"
        lines.append(f"- {w} ({L['session_set']}): faithful band {_pct(L['band']['low'])} .. "
                     f"{_pct(L['band']['high'])}; naive rungs outside it: {out}. "
                     f"Source `{L['source']}` (sha256 `{L['sha256'][:16]}…`).")
    return "\n".join(lines) + "\n"


def ladder_tex(ladder: Dict[str, dict]) -> str:
    wins = [w for w in WINDOW_ORDER if w in ladder]
    tex_lab = {"N0": "naive as-is", "N1": "+ own-price fills", "N2": "+ dated VSD IM",
               "N3": "+ fee on every fill", "F-opt": "Plutus, optimistic queue",
               "F-con": "Plutus, conservative queue"}
    cols = "ll" + "rr" * len(wins)
    head = " & ".join(f"\\multicolumn{{2}}{{c}}{{{w}}}" for w in wins)
    sub = " & ".join("return & fills" for _ in wins)
    rule = " ".join(f"\\cmidrule(lr){{{3 + 2 * i}-{4 + 2 * i}}}" for i in range(len(wins)))
    lines = ["% generated by proto_market_maker.experiments.mm_paper_kit; do not edit",
             "\\begin{tabular}{" + cols + "}", "\\toprule",
             f" & & {head} \\\\", rule, f"rung & environment & {sub} \\\\", "\\midrule"]
    for k in (*NAIVE, "F-opt", "F-con"):
        if k == "F-opt":
            lines.append("\\midrule")
        cells = " & ".join(f"{_tpct(ladder[w]['rungs'][k]['hpr'])} & {ladder[w]['rungs'][k]['fills']}"
                           for w in wins)
        lines.append(f"{k} & {tex_lab[k]} & {cells} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def _f(x, fmt="{:+.2f}"):
    return "--" if x is None else fmt.format(x)


def markout_md(rows: List[dict]) -> str:
    lines = ["| window (sessions) | arm | contracts | taker share | taker impr. (median pt) | "
             "markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | mark switch (M đ) | trading (M đ) |",
             "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for r in rows:
        for arm, a in r["arms"].items():
            m = a["markout_mean_points"]
            ts = a["taker_share"]
            lines.append(
                f"| {r['window']} ({r['session_set']}) | {arm} | {a['contracts']} | "
                f"{_f(ts, '{:.0%}')} | {_f(a['price_improvement_median'])} | {_f(m['1m'])} | "
                f"{_f(m['5m'])} | {_f(m['close'])} | {a['pnl_dong'] / 1e6:+.1f} | "
                f"{a['carry_dong'] / 1e6:+.1f} | {a['mark_switch_dong'] / 1e6:+.1f} | "
                f"{a['trading_dong'] / 1e6:+.1f} |")
    lines += ["", "Markouts: mean per contract in index points, + = good for A. Mark switch: naive's "
                  "revaluation across its F1/F2 stitch (P&L = carry + mark switch + trading). "
                  "Sources: " + ", ".join(f"`{r['source']}` (price path {r['price_path']})" for r in rows)]
    return "\n".join(lines) + "\n"


def markout_tex(rows: List[dict]) -> str:
    lines = ["% generated by proto_market_maker.experiments.mm_paper_kit; do not edit",
             "\\begin{tabular}{llrrrrrrrr}", "\\toprule",
             " & & & & \\multicolumn{3}{c}{markout (pt/contract)} & \\multicolumn{3}{c}{P\\&L (M\\,\\dj)} \\\\",
             "\\cmidrule(lr){5-7} \\cmidrule(lr){8-10}",
             "window & arm & contracts & taker & 1\\,min & 5\\,min & close & total & carry & trading \\\\",
             "\\midrule"]
    for i, r in enumerate(rows):
        if i:
            lines.append("\\midrule")
        for arm, a in r["arms"].items():
            m = a["markout_mean_points"]
            ts = a["taker_share"]
            taker = "--" if ts is None else f"{100 * ts:.0f}\\%"
            lines.append(f"{r['window']} & {arm} & {a['contracts']} & {taker} & "
                         f"${_f(m['1m'])}$ & ${_f(m['5m'])}$ & ${_f(m['close'])}$ & "
                         f"${a['pnl_dong'] / 1e6:+.1f}$ & ${a['carry_dong'] / 1e6:+.1f}$ & "
                         f"${a['trading_dong'] / 1e6:+.1f}$ \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def build(result: Path, out: Path) -> dict:
    ladder = load_ladder(result)
    if not ladder:
        raise SystemExit(f"no ladder results under {result / 'mm_ladder'}")
    marks = load_markouts(result)
    out.mkdir(parents=True, exist_ok=True)
    figure(ladder, out / "mm_ladder")
    (out / "mm_ladder.md").write_text(ladder_md(ladder))
    (out / "mm_ladder.tex").write_text(ladder_tex(ladder))
    written = ["mm_ladder.pdf", "mm_ladder.png", "mm_ladder.md", "mm_ladder.tex"]
    if marks:
        (out / "mm_markout.md").write_text(markout_md(marks))
        (out / "mm_markout.tex").write_text(markout_tex(marks))
        written += ["mm_markout.md", "mm_markout.tex"]
    kit = {"generator": "proto_market_maker.experiments.mm_paper_kit",
           "ladder": ladder, "markouts": marks, "written": written}
    (out / "kit.json").write_text(json.dumps(kit, indent=1) + "\n")
    return kit


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--result", type=Path, default=REPO / "result",
                    help="results root holding mm_ladder/ and mm_markout/")
    ap.add_argument("--out", type=Path, default=REPO / "result" / "paper_kit")
    args = ap.parse_args(argv)
    kit = build(args.result, args.out)
    for w, L in kit["ladder"].items():
        r = L["rungs"]
        print(f"{w}: " + "  ".join(f"{k} {_pct(r[k]['hpr'])}" for k in r)
              + f"  | naive outside band: {L['naive_outside_band']}")
    print(f"markout files: {len(kit['markouts'])}; wrote {', '.join(kit['written'])} to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
