"""Markouts, liquidity and carry/trading P&L for algorithm A's fills (RIVF'26).

The MM ladder (``mm_ladder``) holds algorithm A fixed and changes only the
environment. This module asks *why* the environments disagree, fill by fill:

* **markout** of every fill at +1 min, +5 min and at the session close, in
  index points per contract, signed so that positive is good for A::

      BUY : price(t + h) - fill price        SELL: fill price - price(t + h)

  ``price(t + h)`` is the last print of the fill's contract at or before
  ``t + h`` on the shipped tape (``data/l2/<window>/local_quote_matched``,
  the 00:00:00 end-of-day rows dropped); ``close`` is the official close
  (``data/band/<window>/quote_close``), the price both engines mark to. A
  fill that the market immediately runs through (adverse selection) has a
  negative markout. ``--path rows`` uses A's own row stream instead
  (``mm_faithful_a.naive_rows``: 09:00-14:30, F1 and F2 forward-filled), as
  the first throwaway analysis did.
* **liquidity**: share of contracts filled as taker (``maker`` false) among
  those whose side is known. Naive fills a quote when a print crosses it, so
  it never takes liquidity (``maker`` true); a naive roll or forced reduction
  has no liquidity side (``None``).
* **price improvement** of taker fills vs the order's own limit, in points
  (``limit - price`` for a BUY, ``price - limit`` for a SELL).
* **carry vs trading** decomposition of each arm's daily P&L (real đồng)::

      carry_d   = sum_c position_{d-1}[c] * (close_d[c] - close_{d-1}[c]) * 100 000
      trading_d = pnl_d - carry_d

  i.e. what the overnight inventory earned or lost on the close-to-close move
  of the contract actually held, and everything else (intraday trading,
  fees, the roll). A carried contract with no close on day ``d`` books no
  carry and is counted (``carry_missing_close``).

Session set: the ladder's (``mm_ladder``): all 40 for im2022, the 20
pre-cutover sessions for krx2025; ``--max-sessions K`` keeps the first K.

Inputs per arm (``--fills ARM=PATH``; default: ``result/mm_markout/<window>_fills_<ARM>.json``
when it exists, written by ``mm_fills_trace``). A fills file is either that
trace (``{"fills": [...], "per_session": [...]}``) or a bare list as written by
the earlier throwaway tracer (``ts, side, limit, price, qty, maker``; no
ticker, no role). A fill without a ticker is assigned the contract A traded
that day; on a roll day, the one of the two contracts whose last print is
nearer the fill price (``ticker_inferred`` / ``ticker_ambiguous`` count it).
Naive arms with no file are traced here (``mm_fills_trace.trace_naive``;
fast, no engine). A faithful arm whose file carries no ``per_session``
takes its daily equity and positions from ``result/mm_faithful_a/<window>_<queue>.json``.

Run::

    .venv/bin/python -m proto_market_maker.experiments.mm_markout im2022 \\
        --fills F-opt=<fills_optimistic.json> --fills F-con=<fills_conservative.json>

Writes ``result/mm_markout/<window>[_<tag>]_markout.json`` and ``.md``.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import statistics
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

MULT = 100_000                     # đồng per index point (VN30F)
DEPOSIT_DONG = 500_000_000
HORIZONS: Dict[str, Optional[timedelta]] = {
    "1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "close": None}
ARMS = ("N0", "N3", "F-opt", "F-con")
QUEUE_OF = {"F-opt": "optimistic", "F-con": "conservative"}


# ---------------------------------------------------------------------------
# pure arithmetic
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Fill:
    ts: datetime
    ticker: Optional[str]
    side: str                       # "BUY" | "SELL"
    price: float
    qty: int
    maker: Optional[bool]           # None: no liquidity side (naive roll / forced)
    limit: Optional[float]
    role: str                       # quote | roll | engine | forced | unknown

    def to_json(self) -> dict:
        d = self.__dict__.copy()
        d["ts"] = self.ts.isoformat(sep=" ")
        return d


class PricePath:
    """Last print per contract, as a step function of time."""

    def __init__(self, points: Dict[str, Sequence[Tuple[datetime, float]]]):
        self._t: Dict[str, List[datetime]] = {}
        self._p: Dict[str, List[float]] = {}
        for tk, pts in points.items():
            pts = sorted(pts, key=lambda x: x[0])
            self._t[tk] = [x[0] for x in pts]
            self._p[tk] = [float(x[1]) for x in pts]

    def tickers(self):
        return self._t.keys()

    def at(self, ticker: str, ts: datetime) -> float:
        """Last print at or before ``ts`` (the first print if ``ts`` precedes it)."""
        i = bisect.bisect_right(self._t[ticker], ts) - 1
        return self._p[ticker][max(i, 0)]

    def last_on(self, ticker: str, day: date) -> float:
        end = datetime.combine(day, datetime.max.time())
        return self.at(ticker, end)


def _sign(side: str) -> int:
    return 1 if side == "BUY" else -1


def markouts(fill: Fill, path: PricePath, closes: Dict[Tuple[date, str], float]) -> Dict[str, float]:
    """Per-contract markout of one fill at each horizon, points, + = good for A."""
    out = {}
    for name, h in HORIZONS.items():
        if h is None:
            ref = closes.get((fill.ts.date(), fill.ticker))
            if ref is None:
                ref = path.last_on(fill.ticker, fill.ts.date())
        else:
            ref = path.at(fill.ticker, fill.ts + h)
        out[name] = _sign(fill.side) * (ref - fill.price)
    return out


def price_improvement(fill: Fill) -> Optional[float]:
    if fill.limit is None:
        return None
    return (fill.limit - fill.price) if fill.side == "BUY" else (fill.price - fill.limit)


def _block(fills: List[Fill], marks: List[Dict[str, float]]) -> dict:
    n = sum(f.qty for f in fills)
    tot = {h: sum(m[h] * f.qty for f, m in zip(fills, marks)) for h in HORIZONS}
    return {"fills": len(fills), "contracts": n,
            "markout_mean_points": {h: (tot[h] / n if n else None) for h in HORIZONS},
            "markout_total_points": tot,
            "markout_total_dong": {h: tot[h] * MULT for h in HORIZONS}}


def summarise(fills: List[Fill], path: PricePath,
              closes: Dict[Tuple[date, str], float]) -> dict:
    marks = [markouts(f, path, closes) for f in fills]
    out = _block(fills, marks)
    groups = {"maker": True, "taker": False, "unknown": None}
    out["by_liquidity"] = {}
    for g, v in groups.items():
        sel = [(f, m) for f, m in zip(fills, marks) if f.maker is v]
        out["by_liquidity"][g] = _block([f for f, _ in sel], [m for _, m in sel])
    known = out["by_liquidity"]["maker"]["contracts"] + out["by_liquidity"]["taker"]["contracts"]
    out["taker_share"] = (out["by_liquidity"]["taker"]["contracts"] / known) if known else None
    imp = [price_improvement(f) for f in fills if f.maker is False]
    imp = [x for x in imp if x is not None]
    out["price_improvement_points"] = {
        "n": len(imp), "median": statistics.median(imp) if imp else None,
        "mean": (sum(imp) / len(imp)) if imp else None,
        "min": min(imp) if imp else None, "max": max(imp) if imp else None,
        "sum": sum(imp)}
    roles: Dict[str, int] = {}
    for f in fills:
        roles[f.role] = roles.get(f.role, 0) + f.qty
    out["by_role"] = roles
    out["close_from_last_print"] = sum(1 for f in fills if (f.ts.date(), f.ticker) not in closes)
    return out


def decompose(days: Sequence[date], pnl_dong: Sequence[float],
              end_positions: Sequence[Dict[str, int]],
              closes: Dict[Tuple[date, str], float]) -> dict:
    """Daily P&L = carry (yesterday's positions x today's close-to-close move) + trading."""
    carry = trading = 0.0
    missing = 0
    rows = []
    prev: Dict[str, int] = {}
    for i, d in enumerate(days):
        c = 0.0
        if i > 0:
            for tk, q in prev.items():
                a, b = closes.get((days[i - 1], tk)), closes.get((d, tk))
                if not q:
                    continue
                if a is None or b is None:
                    missing += 1
                    continue
                c += q * (b - a) * MULT
        tr = pnl_dong[i] - c
        carry += c
        trading += tr
        rows.append({"date": d.isoformat(), "pnl_dong": pnl_dong[i], "carry_dong": c,
                     "trading_dong": tr, "end_positions": dict(end_positions[i])})
        prev = end_positions[i]
    return {"carry_dong": carry, "trading_dong": trading, "total_dong": carry + trading,
            "carry_missing_close": missing, "per_session": rows}


def infer_tickers(fills: Iterable[Fill], path: PricePath,
                  candidates: Callable[[datetime], Tuple[str, ...]],
                  ambiguous_within: float = 1.0) -> Tuple[List[Fill], int]:
    """Give a ticker to fills that have none: the only candidate, or the
    candidate whose last print is nearest the fill price. A pick whose
    distance beats the runner-up by less than ``ambiguous_within`` points is
    counted as ambiguous."""
    out, amb = [], 0
    for f in fills:
        if f.ticker is not None:
            out.append(f)
            continue
        cands = candidates(f.ts)
        if len(cands) == 1:
            out.append(replace(f, ticker=cands[0]))
            continue
        dist = sorted((abs(path.at(tk, f.ts) - f.price), tk) for tk in cands)
        if dist[1][0] - dist[0][0] < ambiguous_within:
            amb += 1
        out.append(replace(f, ticker=dist[0][1]))
    return out, amb


def _opt_float(x) -> Optional[float]:
    return None if x is None else float(x)


def fill_from_dict(r: dict) -> Fill:
    return Fill(ts=datetime.fromisoformat(str(r["ts"])), ticker=r.get("ticker"),
                side=str(r["side"]), price=float(r["price"]), qty=int(r.get("qty", 1)),
                maker=None if r.get("maker") is None else bool(r["maker"]),
                limit=_opt_float(r.get("limit")), role=r.get("role") or "unknown")


def load_fills(path: Path) -> List[Fill]:
    raw = json.loads(Path(path).read_text())
    rows = raw["fills"] if isinstance(raw, dict) else raw
    return [fill_from_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# data (shipped slices only)
# ---------------------------------------------------------------------------

def load_closes(window: str) -> Dict[Tuple[date, str], float]:
    import pandas as pd
    from proto_market_maker.experiments import mm_anchor as A
    band, _ = A._roots(window)
    c = pd.read_parquet(Path(band) / "quote_close.parquet")
    return {(pd.Timestamp(d).date(), t): float(p)
            for d, t, p in zip(c["datetime"], c["tickersymbol"], c["price"])}


def tape_path(window: str, days: Sequence[date]) -> PricePath:
    """Every print of every contract on the session days (00:00:00 EOD rows dropped)."""
    import pandas as pd
    from proto_market_maker.experiments import mm_anchor as A
    _, l2 = A._roots(window)
    m = pd.read_parquet(Path(l2) / "local_quote_matched.parquet")
    m = m[m["datetime"].dt.date.isin(set(days))]
    t = m["datetime"].dt
    m = m[~((t.hour == 0) & (t.minute == 0) & (t.second == 0))]
    pts: Dict[str, list] = {}
    for tk, g in m.groupby("tickersymbol"):
        pts[tk] = list(zip(g["datetime"].dt.to_pydatetime(), g["price"].astype(float)))
    return PricePath(pts)


def rows_path(data) -> PricePath:
    """A's own row stream: F1 and F2 last prices, forward-filled, 09:00-14:30."""
    pts: Dict[str, list] = {}
    ts = data["datetime"].dt.to_pydatetime()
    for tcol, pcol in (("tickersymbol", "price"), ("f2-tickersymbol", "f2_price")):
        for t, tk, p in zip(ts, data[tcol], data[pcol]):
            if tk is None or p is None or tk != tk:
                continue
            pts.setdefault(tk, []).append((t, float(p)))
    return PricePath(pts)


def session_set(window: str, max_sessions: Optional[int] = None):
    from proto_market_maker.experiments import mm_anchor as A
    fcc, all_days = A.load_contract_map(window)
    days = [d for d in all_days if d < A.KRX_CUTOVER] if window == "krx2025" else list(all_days)
    if max_sessions:
        days = days[:max_sessions]
    return fcc, all_days, days


def contract_candidates(window: str):
    """ts -> the contracts A trades that day: F1 (F2 on its roll day), plus F1 on a roll day."""
    from proto_market_maker.experiments import mm_anchor as A
    from proto_market_maker.experiments.windows import roll_days
    fcc, all_days = A.load_contract_map(window)
    rolls = set(roll_days(all_days))

    def cand(ts: datetime):
        d = ts.date()
        if d in rolls:
            return (fcc[(d, "VN30F2M")], fcc[(d, "VN30F1M")])
        return (fcc[(d, "VN30F1M")],)
    return cand


# ---------------------------------------------------------------------------
# per-arm assembly
# ---------------------------------------------------------------------------

def _per_session_from_result(window: str, queue: str):
    from proto_market_maker.experiments import mm_anchor as A
    p = A.REPO / "result" / "mm_faithful_a" / f"{window}_{queue}.json"
    raw = p.read_bytes()
    return json.loads(raw)["per_session"], {"path": str(p.relative_to(A.REPO)),
                                            "sha256": hashlib.sha256(raw).hexdigest()}


def arm_inputs(window: str, arm: str, fills_file: Optional[Path], max_sessions, log):
    """-> (fills, per_session records, provenance dict)."""
    from proto_market_maker.experiments import mm_anchor as A
    prov: dict = {}
    per_session = None
    if fills_file is None:
        default = A.REPO / "result" / "mm_markout" / f"{window}_fills_{arm}.json"
        if default.exists():
            fills_file = default
    if fills_file is not None:
        raw = Path(fills_file).read_bytes()
        prov = {"fills_file": Path(fills_file).name, "fills_sha256": hashlib.sha256(raw).hexdigest()}
        doc = json.loads(raw)
        fills = [fill_from_dict(r) for r in (doc["fills"] if isinstance(doc, dict) else doc)]
        if isinstance(doc, dict):
            per_session = doc.get("per_session")
            for k in ("plutus_simulator_commit", "sessions", "arm"):
                if k in doc:
                    prov[k] = doc[k]
    elif arm.startswith("N"):
        from proto_market_maker.experiments.mm_fills_trace import trace_naive
        doc = trace_naive(window, int(arm[1:]), max_sessions=max_sessions, log=log)
        fills = [fill_from_dict(r) for r in doc["fills"]]
        per_session = doc["per_session"]
        prov = {"traced_here": True}
    else:
        raise SystemExit(f"{arm}: no fills file (pass --fills {arm}=PATH or run mm_fills_trace)")
    if per_session is None:
        if arm not in QUEUE_OF:
            raise SystemExit(f"{arm}: the fills file has no per_session block")
        per_session, src = _per_session_from_result(window, QUEUE_OF[arm])
        prov["per_session_from"] = src
    return fills, per_session, prov


def analyse_arm(arm, fills, per_session, days, path, closes, cand) -> dict:
    keep = set(days)
    fills = [f for f in fills if f.ts.date() in keep]
    missing = sum(1 for f in fills if f.ticker is None)
    fills, amb = infer_tickers(fills, path, cand)
    recs = {date.fromisoformat(r["date"]): r for r in per_session}
    span = [d for d in days if d in recs]
    eq = [float(DEPOSIT_DONG)] + [float(recs[d]["end_equity_dong"]) for d in span]
    pnl = [eq[i + 1] - eq[i] for i in range(len(span))]
    pos = [{k: int(v) for k, v in (recs[d].get("positions") or {}).items() if int(v)} for d in span]
    dec = decompose(span, pnl, pos, closes)
    out = summarise(fills, path, closes)
    out.update({"arm": arm, "sessions": len(span),
                "sessions_with_fills": len({f.ts.date() for f in fills}),
                "ticker_inferred": missing, "ticker_ambiguous": amb,
                "pnl_dong": dec["total_dong"], "hpr": eq[-1] / eq[0] - 1.0,
                "carry_dong": dec["carry_dong"], "trading_dong": dec["trading_dong"],
                "carry_missing_close": dec["carry_missing_close"],
                "mean_abs_end_inventory": (sum(abs(sum(p.values())) for p in pos) / len(pos)) if pos else None,
                "per_session": dec["per_session"]})
    if span != list(days):
        out["sessions_missing"] = [d.isoformat() for d in days if d not in recs]
    return out


def run(window: str, files: Dict[str, Path], arms=ARMS, max_sessions=None,
        path_kind: str = "tape", log=print) -> dict:
    from proto_market_maker.experiments import mm_anchor as A
    fcc, all_days, days = session_set(window, max_sessions)
    closes = load_closes(window)
    if path_kind == "rows":
        from proto_market_maker.experiments.mm_faithful_a import naive_rows
        path = rows_path(naive_rows(window, days, fcc))
    else:
        path = tape_path(window, days)
    cand = contract_candidates(window)
    out_arms, prov = {}, {}
    for arm in arms:
        fills, per_session, p = arm_inputs(window, arm, files.get(arm), max_sessions, log)
        out_arms[arm] = analyse_arm(arm, fills, per_session, days, path, closes, cand)
        prov[arm] = p
        a = out_arms[arm]
        log(f"{arm}: contracts={a['contracts']} taker={a['taker_share']} "
            f"5m={a['markout_mean_points']['5m']} trading={a['trading_dong'] / 1e6:.1f}M")
    return {"window": window,
            "session_set": ("20 pre-cutover sessions" if window == "krx2025" else "all 40 sessions")
                           + (f", first {max_sessions}" if max_sessions else ""),
            "sessions": [d.isoformat() for d in days],
            "price_path": path_kind, "horizons": list(HORIZONS),
            "units": "markouts in index points per contract (+ = good for A); P&L in real đồng",
            "arms": out_arms, "inputs": prov,
            "plutus_simulator_head": A._engine_commit()}


def _f(x, fmt="{:+.2f}"):
    return "" if x is None else fmt.format(x)


def markdown(out: dict) -> str:
    lines = [f"### {out['window']}: markouts ({out['session_set']}; price path: {out['price_path']})", "",
             "| arm | sessions | contracts | taker share | taker price impr. (median, pts) | "
             "markout 1 min | 5 min | close | P&L (M đ) | carry (M đ) | trading (M đ) |",
             "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for arm, a in out["arms"].items():
        m = a["markout_mean_points"]
        ts = a["taker_share"]
        lines.append(
            f"| {arm} | {a['sessions']} | {a['contracts']} | {'' if ts is None else f'{ts:.0%}'} | "
            f"{_f(a['price_improvement_points']['median'])} | {_f(m['1m'])} | {_f(m['5m'])} | "
            f"{_f(m['close'])} | {a['pnl_dong'] / 1e6:+.1f} | {a['carry_dong'] / 1e6:+.1f} | "
            f"{a['trading_dong'] / 1e6:+.1f} |")
    notes = []
    for arm, a in out["arms"].items():
        if a["ticker_inferred"]:
            notes.append(f"{arm}: {a['ticker_inferred']} fills had no contract and were assigned one "
                         f"({a['ticker_ambiguous']} ambiguous).")
        if a["carry_missing_close"]:
            notes.append(f"{arm}: {a['carry_missing_close']} carried positions had no close (no carry booked).")
        if a.get("sessions_missing"):
            notes.append(f"{arm}: no equity record for {len(a['sessions_missing'])} sessions.")
    lines += ["", "Markouts: mean per contract, index points, + = good for A (1 point = 100,000 đ "
                  "per contract). Taker share: contracts filled as taker among those with a liquidity "
                  "side. Carry = previous end positions x close-to-close move; trading = the rest."]
    if notes:
        lines += [""] + [f"- {n}" for n in notes]
    lines += ["", "Inputs:", ""]
    for arm, p in out.get("inputs", {}).items():
        if p.get("traced_here"):
            src = "naive trace run by this module"
        else:
            src = f"`{p['fills_file']}` (sha256 `{p['fills_sha256'][:16]}…`)"
        if p.get("per_session_from"):
            src += f"; equity from `{p['per_session_from']['path']}`"
        lines.append(f"- {arm}: {src}")
    return "\n".join(lines) + "\n"


def _parse_files(items) -> Dict[str, Path]:
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        if k not in ARMS or not v:
            raise SystemExit(f"--fills expects ARM=PATH with ARM in {ARMS}: {it}")
        out[k] = Path(v)
    return out


def main(argv=None) -> int:
    from proto_market_maker.experiments import mm_anchor as A
    from proto_market_maker.experiments.windows import WINDOWS
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("window", choices=sorted(WINDOWS))
    ap.add_argument("--fills", action="append", metavar="ARM=PATH",
                    help="fills file for an arm (N0, N3, F-opt, F-con); repeatable")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument("--path", choices=("tape", "rows"), default="tape")
    ap.add_argument("--tag", default=None, help="output name suffix, e.g. first6")
    ap.add_argument("--out-dir", type=Path, default=A.REPO / "result" / "mm_markout")
    args = ap.parse_args(argv)
    out = run(args.window, _parse_files(args.fills), arms=tuple(args.arms.split(",")),
              max_sessions=args.max_sessions, path_kind=args.path)
    stem = f"{args.window}_{args.tag}" if args.tag else args.window
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{stem}_markout.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    md = markdown(out)
    (args.out_dir / f"{stem}_markout.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
