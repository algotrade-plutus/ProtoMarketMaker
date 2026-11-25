"""Trace every fill of algorithm A in one environment (RIVF'26 MM markouts).

Arms (A fixed, environment varied, as in ``mm_ladder``):

* ``N0`` .. ``N3``: the naive engine rungs (``naive_variants``; pure, fast).
  Quote fills are recorded at the price the rung books (N0: the crossing
  print; N1+: the quote's own price), ``maker`` true (a resting quote crossed
  by a print), ``limit`` the quote. The roll (``move_f1_to_f2``: close F1 at
  the F1 print, open F2 at the F2 print) and forced reductions
  (``handle_force_sell``) are recorded with role ``roll`` / ``forced`` and no
  liquidity side. Session set: the ladder's (every session of the window;
  krx2025's pre/post-cutover views are cut from it by ``mm_markout``).
* ``F-opt`` / ``F-con``: Plutus faithful-A (``mm_faithful_a.run_faithful_a``)
  with the optimistic / conservative queue, all window sessions; every fill
  event as the engine reports it (``maker`` from the fill detail), with the
  order's role (quote, roll, engine).

Each output also carries the per-session equity and end positions, so
``mm_markout`` can decompose P&L into carry and trading from the trace alone.

A faithful session takes minutes (the whole window: tens of minutes to hours
per arm), so ``--log FILE`` is required: one flushed line per session with the
date, contract, fills, equity, elapsed time and ETA.

Run::

    .venv/bin/python -m proto_market_maker.experiments.mm_fills_trace im2022 --arm F-opt \\
        --log /path/to/trace_im2022_F-opt.log

Writes ``result/mm_markout/<window>_fills_<arm>.json`` (or ``--out``).
"""
from __future__ import annotations

import argparse
import json
import sys
import time as _time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

ARMS = ("N0", "N1", "N2", "N3", "F-opt", "F-con")
QUEUE_OF = {"F-opt": "optimistic", "F-con": "conservative"}
ARM_OF = {q: a for a, q in QUEUE_OF.items()}


class ProgressLog:
    """One line per session to a named file (line-buffered, flushed) and stdout."""

    def __init__(self, path: Optional[Path], total: int, label: str):
        self.total, self.label, self.k, self.t0 = total, label, 0, _time.time()
        self.fh = None
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.fh = open(path, "a", buffering=1, encoding="utf-8")
        self.note(f"start {label}: {total} sessions")

    def note(self, msg: str):
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        if self.fh is not None:
            self.fh.write(line + "\n")
            self.fh.flush()

    def __call__(self, msg: str):
        """Called once per finished session."""
        self.k += 1
        el = _time.time() - self.t0
        rate = el / self.k
        eta = rate * max(self.total - self.k, 0)
        self.note(f"{msg.strip()} | session {self.k}/{self.total}, elapsed {el:.0f}s, "
                  f"{rate:.0f}s/session, ETA {eta / 60:.1f} min")

    def close(self):
        self.note(f"done {self.label}: {self.k} sessions in {_time.time() - self.t0:.0f}s")
        if self.fh is not None:
            self.fh.close()


def _naive_tracer_class():
    from proto_market_maker.naive_variants import NaiveVariant

    class NaiveTracer(NaiveVariant):
        """``NaiveVariant`` that records each fill; A's loop is inherited unchanged."""

        def __init__(self, capital, options, contracts, log):
            super().__init__(capital, options, printable=False)
            self._contracts = contracts         # date -> (F1 ticker, F2 ticker)
            self._rolled = False
            self._log = log
            self._day_fills = 0
            self.trace = []
            self.per_session = []

        def _ticker(self, which: Optional[int] = None) -> str:
            tk1, tk2 = self._contracts[self.cur_date.date()]
            if which is None:
                which = 2 if self._rolled else 1
            return tk2 if which == 2 else tk1

        def _rec(self, side, price, qty, maker, limit, role, ticker):
            self.trace.append({"ts": self.cur_date.isoformat(sep=" "), "ticker": ticker,
                               "side": side, "price": str(price), "qty": int(qty),
                               "maker": maker, "limit": None if limit is None else str(limit),
                               "role": role})
            self._day_fills += int(qty)

        def move_f1_to_f2(self, f1_price, f2_price):
            q = self.inventory
            super().move_f1_to_f2(f1_price, f2_price)
            if q:
                self._rec("SELL" if q > 0 else "BUY", f1_price, abs(q), None, None, "roll",
                          self._ticker(1))
                self._rec("BUY" if q > 0 else "SELL", f2_price, abs(q), None, None, "roll",
                          self._ticker(2))
            self._rolled = True

        def handle_force_sell(self, price):
            before = self.inventory
            super().handle_force_sell(price)
            d = self.inventory - before
            if d:
                self._rec("BUY" if d > 0 else "SELL", price, abs(d), None, None, "forced",
                          self._ticker())

        def handle_matched_order(self, price):
            inv0, bid, ask = self.inventory, self.bid_price, self.ask_price
            m = super().handle_matched_order(price)
            d = self.inventory - inv0
            own = self.options.own_price_fills
            if d > 0:
                self._rec("BUY", bid if own else price, d, True, bid, "quote", self._ticker())
            elif d < 0:
                self._rec("SELL", ask if own else price, -d, True, ask, "quote", self._ticker())
            return m

        def update_pnl(self, close_price):
            super().update_pnl(close_price)
            d = self.cur_date.date()
            tk = self._ticker()
            eq = float(self.daily_assets[-1]) * 1000      # naive units: thousand đồng
            self.per_session.append({"date": d.isoformat(), "contract": tk,
                                     "mark_contract": tk, "rolled": self._rolled,
                                     "fills": self._day_fills,
                                     "end_net": self.inventory,
                                     "positions": {tk: self.inventory} if self.inventory else {},
                                     "end_equity_dong": eq})
            self._log(f"[naive] {d} {tk} fills={self._day_fills} net={self.inventory} eq={eq:,.0f}")
            self._rolled = False
            self._day_fills = 0

    return NaiveTracer


def trace_naive(window: str, rung: int, max_sessions: Optional[int] = None, log=print) -> dict:
    from proto_market_maker.experiments import mm_anchor as A
    from proto_market_maker.experiments.mm_faithful_a import naive_rows
    from proto_market_maker.naive_variants import NaiveOptions
    fcc, all_days = A.load_contract_map(window)
    days = list(all_days)
    if max_sessions:
        days = days[:max_sessions]
    data = naive_rows(window, days, fcc)
    contracts = {d: (fcc[(d, "VN30F1M")], fcc[(d, "VN30F2M")]) for d in days}
    bt = _naive_tracer_class()(Decimal("5e5"), NaiveOptions.rung(rung), contracts, log)
    t0 = _time.time()
    bt.run(data.copy(), A.step_param())
    return {"window": window, "arm": f"N{rung}", "environment": "naive engine",
            "options": NaiveOptions.rung(rung).__dict__,
            "sessions": len(bt.per_session),
            "session_set": f"all {len(bt.per_session)} sessions"
                           + (f", first {max_sessions}" if max_sessions else ""),
            "fills_counted_by_engine": bt.fills, "forced_reductions": bt.forced_reductions,
            "units": "prices in index points; equity in real đồng",
            "fills": bt.trace, "per_session": bt.per_session,
            "wall_seconds": round(_time.time() - t0, 1)}


def trace_faithful(window: str, arm: str, max_sessions: Optional[int] = None, log=print) -> dict:
    from proto_market_maker.experiments import mm_faithful_a as FA
    fills = []
    out = FA.run_faithful_a(window, QUEUE_OF[arm], log=log, max_sessions=max_sessions,
                            on_fill=fills.append)
    return faithful_trace_doc(window, arm, out, fills)


def faithful_trace_doc(window: str, arm: str, out: dict, fills: list) -> dict:
    """The trace document for one faithful-A run's result and its fill events
    (shared with ``mm_faithful_a --trace-out``, which records them in its own run)."""
    run = {k: v for k, v in out.items() if k not in ("per_session",)}
    return {"window": window, "arm": arm, "environment": "Plutus faithful-A",
            "queue": QUEUE_OF[arm], "sessions": out["sessions"],
            "plutus_simulator_commit": out["plutus_simulator_commit"],
            "plutus_simulator_src_dirty": out["plutus_simulator_src_dirty"],
            "plutus_simulator_commit_at_end": out["plutus_simulator_commit_at_end"],
            "units": "prices in index points; equity in real đồng",
            "fills": fills, "per_session": out["per_session"], "run": run}


def main(argv=None) -> int:
    from proto_market_maker.experiments import mm_anchor as A
    from proto_market_maker.experiments.windows import WINDOWS
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("window", choices=sorted(WINDOWS))
    ap.add_argument("--arm", choices=ARMS, required=True)
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument("--log", type=Path, required=True,
                    help="progress log file: one flushed line per session")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    _, all_days = A.load_contract_map(args.window)
    total = min(len(all_days), args.max_sessions or len(all_days))
    plog = ProgressLog(args.log, total, f"{args.window} {args.arm}")
    if args.arm.startswith("N"):
        out = trace_naive(args.window, int(args.arm[1:]), args.max_sessions, log=plog)
    else:
        out = trace_faithful(args.window, args.arm, args.max_sessions, log=plog)
    path = args.out or (A.REPO / "result" / "mm_markout" / f"{args.window}_fills_{args.arm}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=str) + "\n")
    plog.note(f"wrote {path} ({len(out['fills'])} fill events)")
    plog.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
