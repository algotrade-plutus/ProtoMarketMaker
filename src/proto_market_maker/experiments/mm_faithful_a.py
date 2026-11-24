"""Faithful-A: the naive MarketMaker algorithm A, executed by Plutus (RIVF'26).

Owner framing: the naive engine's *behaviour* is the algorithm A under study;
the naive engine (N) and Plutus (F) are only environments. This arm therefore
runs A exactly and lets only the environment differ. Compared with the
``mm_anchor`` faithful arm (left untouched) it differs on four points:

#1  **Inventory is carried overnight.** One multi-day ``ExchangeSession`` spans
    the whole window, so the engine applies daily variation-margin settlement
    (``DerivativesAccount.settle_daily`` at the close), the dated VSD IM, the
    margin ladder (warning / call / forced liquidation, the latter executed by
    the engine with real orders) and expiry settlement. Naive's
    ``handle_force_sell`` is NOT ported: in F the engine's margin machinery
    replaces it.
#7  **Quoting window 09:00-14:30:59**, naive's own rows (``_naive_frames``
    keeps hour 14 up to minute 30). Quotes still resting at 14:30 enter the
    closing auction under the engine's rules; the session is advanced through
    the ATC to 15:00 each day so the close, the expiry and the daily
    settlement run.
#8  **Roll like A.** On naive's roll trigger (``get_expired_dates`` /
    ``move_f1_to_f2``: the first row of the session whose next session is on or
    after the front month's expiry) A sends real orders: close the F1 position
    and open the same signed position in F2, each a marketable LIMIT one point
    through the opposite touch. A's roll is instantaneous in naive, so in F a
    leg that is refused or unfilled is cancelled (if live) and resubmitted for
    its remainder on A's next timed requote tick (15 s) until it is done or the
    session ends (``roll_retries``, ``roll_unfilled_contracts``). Fills are
    whatever F gives.
#11 **Same decision clock.** F's clock steps on the same merged F1/F2 rows naive
    iterates (``Backtesting.prepare`` over ``mm_anchor._naive_frames``), and A
    quotes off the same row price (F1, or F2 while rolling) with the same rule:
    ``quote(price, inventory, step)``, requoted when 15 s have passed since the
    last timed requote or right after a fill; quotes reset at each day's end.
    The contract quoted is the row's (``tickersymbol`` or ``f2-tickersymbol``).
    A's inventory is the account's net contracts across all VN30F contracts.

No regime guard: A has none. From the 2025-05-05 KRX cutover the engine's
``margin_model()`` raises ``UnresolvedRule``; the engine still margins on the
pre-KRX shape and counts ``margin_model_unsourced`` blindness. That is reported,
not hidden (``post`` split for krx2025).

P&L is the harness's own ledger, real dong: cash from every fill (quote, roll,
engine forced close) and expiry settlement, net position marked at the day's
close (``quote_close``), minus the engine's charges. The engine's deposit
balance is recorded alongside as a cross-check.

Run::

    .venv/bin/python -m proto_market_maker.experiments.mm_faithful_a im2022 --queue optimistic

Writes ``result/mm_faithful_a/<window>_<queue>.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time as _time
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from proto_market_maker.backtest import Backtesting
from proto_market_maker.experiments import mm_anchor as A
from proto_market_maker.experiments.windows import WINDOWS
from proto_market_maker.strategy import quote
from proto_market_maker.utils import get_expired_dates

DAY_END = time(15, 0)                 # advance here after the last row: ATC, close, settlement
ATC_FROM = time(14, 30)
THROUGH = Decimal("1.0")              # points through the opposite touch (roll legs)


def naive_rows(window: str, sessions: List[date], fcc) -> pd.DataFrame:
    """Exactly the row stream ``mm_anchor.run_naive`` feeds the naive engine."""
    f1, f2 = A._naive_frames(window, sessions, fcc)
    data = Backtesting.prepare(f1, f2)
    first = data[data["f2_price"].notna() & data["price"].notna()].index[0]
    return data.loc[first:].reset_index(drop=True)


def _session(start: date, end: date, deposit: int, queue: str, source):
    from plutus.market.session import ExchangeSession, parse_config
    from plutus.execution import PlutusBackend
    config = parse_config({
        "period": {"start": start.isoformat(),
                   "end": (end + timedelta(days=1)).isoformat()},
        "resolution": "tick",
        "exchange_rules": {"venues": ["HNXDS"]},
        "accounts": {"derivatives": {"initial_deposit": deposit,
                                     "account_no": "DER-MM-A"}},
        "fill_policy": {"kind": "book_walk", "queue": queue,
                        "max_participation": None, "max_staleness": None},
    })
    return PlutusBackend(ExchangeSession.build(config, source=source))


def run_faithful_a(window: str, queue: str, log=print, max_sessions: Optional[int] = None) -> dict:
    from plutus.market.adapters.book_session import BookSessionSource
    from plutus.market.protocol import Order
    from plutus.core.order import OrderType, Side
    from plutus.market.session import Accepted, Cancelled

    # The engine code a run uses is the code imported at its start; record that
    # commit, and the one at the end, so a checkout that moves mid-run shows.
    commit_at_start = A._engine_commit()
    dirty_at_start = A._engine_dirty()
    fcc, sessions = A.load_contract_map(window)
    step = A.step_param()
    band, l2 = A._roots(window)
    source = BookSessionSource.for_roots(band, l2)
    data = naive_rows(window, sessions, fcc)
    closes = pd.read_parquet(Path(band) / "quote_close.parquet")
    close_of = {(pd.Timestamp(d).date(), t): Decimal(str(p))
                for d, t, p in zip(closes["datetime"], closes["tickersymbol"], closes["price"])}

    trading_dates = data["date"].unique().tolist()
    if max_sessions:
        trading_dates_run = trading_dates[:max_sessions]
    else:
        trading_dates_run = trading_dates
    run_set = set(trading_dates_run)
    backend = _session(trading_dates[0], trading_dates[-1], A.DEPOSIT_DONG, queue, source)
    sess = backend.session

    # ---- harness ledger --------------------------------------------------
    cash = Decimal(0)
    pos: Dict[str, int] = {}
    last_px: Dict[str, Decimal] = {}
    side_of: Dict[str, object] = {}       # every order we submitted
    role_of: Dict[str, str] = {}          # quote | roll
    live_quotes: Dict[str, object] = {}
    roll_legs: List[dict] = []            # A's roll legs today: {ticker, side, qty, oid, tries}
    roll_by_oid: Dict[str, dict] = {}
    ind_orders = set()
    tot = Counter()
    refusals = Counter()
    per_session = []
    margin_events = []
    s = Counter()

    def net() -> int:
        return sum(pos.values())

    def side_lookup(oid):
        if oid in side_of:
            return side_of[oid]
        for rec in sess.orders():
            if rec.order_id == oid:
                side_of[oid] = rec.order.side
                role_of[oid] = "engine"
                return rec.order.side
        return None

    def absorb(events) -> bool:
        nonlocal cash
        quote_filled = False
        for e in events:
            k = A._kind(e)
            if k in ("filled", "partially_filled"):
                side = side_lookup(e.order_id)
                q, px = int(e.quantity), Decimal(str(e.price))
                sgn = 1 if side is Side.BUY else -1
                cash -= sgn * px * q * A.MULT
                before = pos.get(e.ticker, 0)
                if before * sgn < 0:          # position-reducing contracts
                    s["closing_fills"] += min(q, abs(before))
                pos[e.ticker] = before + sgn * q
                role = role_of.get(e.order_id, "engine")
                s["fills"] += q
                s[f"{role}_fills"] += q
                s["maker_fills" if e.detail.get("maker") else "taker_fills"] += q
                if role == "quote":
                    quote_filled = True
                leg = roll_by_oid.get(e.order_id)
                if leg is not None:
                    leg["qty"] -= q
                    if leg["qty"] <= 0 or k == "filled":
                        roll_by_oid.pop(e.order_id, None)
                        leg["oid"] = None
                if k == "filled":
                    live_quotes.pop(e.order_id, None)
            elif k in ("cancelled", "expired"):
                live_quotes.pop(e.order_id, None)
                leg = roll_by_oid.pop(e.order_id, None)
                if leg is not None:
                    leg["oid"] = None             # not live: resubmitted on the next tick
                if k == "expired":
                    if role_of.get(e.order_id) == "quote":
                        s["quote_expired"] += 1
            elif k == "indeterminate":
                s["indeterminate_evals"] += 1
                if e.ts.time() >= ATC_FROM:
                    s["indeterminate_evals_atc"] += 1
                if e.order_id not in ind_orders:
                    ind_orders.add(e.order_id)
                    s["indeterminate_orders"] += 1
                    if role_of.get(e.order_id) == "quote" and e.ts.time() >= ATC_FROM:
                        s["indeterminate_orders_atc"] += 1
            elif k in ("margin_warning", "margin_call", "margin_call_cleared",
                       "forced_liquidation"):
                s[k] += 1
                ev = {"ts": e.ts.isoformat(), "kind": k}
                if k == "forced_liquidation":
                    ev["executed"] = bool(e.detail.get("executed"))
                    ev["closed"] = [list(map(str, c)) for c in (e.detail.get("closed") or ())]
                    s["forced_liquidation_executed"] += int(ev["executed"])
                margin_events.append(ev)
            elif k == "expiry_settled":
                q, px = int(e.quantity), Decimal(str(e.price))
                cash += q * px * A.MULT
                pos[e.ticker] = pos.get(e.ticker, 0) - q
                s["expiry_settled_contracts"] += abs(q)
        return quote_filled

    def submit(ticker, side, qty, px, role) -> Optional[str]:
        ack = backend.submit(Order(ticker=ticker, side=side, quantity=qty,
                                   order_type=OrderType.LIMIT,
                                   limit_price=px.quantize(Decimal("0.1"))))
        s[f"{role}_submitted"] += 1
        if isinstance(ack, Accepted):
            side_of[ack.order_id] = side
            role_of[ack.order_id] = role
            return ack.order_id
        rule = getattr(ack.rule, "name", str(ack.rule))
        refusals[f"{role}:{rule}"] += 1
        s[f"{role}_rejected"] += 1
        return None

    def cancel(oid):
        r = backend.cancel(oid)
        if isinstance(r, Cancelled):
            return True
        s["cancel_refused"] += 1
        refusals[f"cancel:{getattr(getattr(r, 'rule', None), 'name', 'refused')}"] += 1
        return False

    def requote(ticker, price):
        for oid in list(live_quotes):
            cancel(oid)
            live_quotes.pop(oid, None)     # A replaces its quote either way
        bid, ask = quote(price, net(), step)
        for side, px in ((Side.BUY, bid), (Side.SELL, ask)):
            oid = submit(ticker, side, 1, px, "quote")
            if oid is not None:
                live_quotes[oid] = side

    def send_leg(leg, ts, ref_price):
        """(Re)submit a roll leg's remainder, a marketable LIMIT one point
        through the opposite touch. A keeps trying: a refused or unfilled leg
        is resubmitted on A's next requote tick (15 s) until done or the
        session ends."""
        book = source.book_at(leg["ticker"], ts)
        touch = None
        if book is not None:
            lvl = book.bid.best if leg["side"] is Side.SELL else book.ask.best
            touch = lvl.price if lvl is not None else None
        base = touch if touch is not None else ref_price
        if base is None:
            s["roll_no_price"] += 1
            return
        px = base - THROUGH if leg["side"] is Side.SELL else base + THROUGH
        if leg["tries"]:
            s["roll_retries"] += 1
        leg["tries"] += 1
        oid = submit(leg["ticker"], leg["side"], leg["qty"], px, "roll")
        if oid is not None:
            leg["oid"] = oid
            roll_by_oid[oid] = leg

    def new_leg(ticker, side, qty, ts, ref_price):
        leg = {"ticker": ticker, "side": side, "qty": qty, "oid": None, "tries": 0}
        roll_legs.append(leg)
        send_leg(leg, ts, ref_price)

    def retry_rolls(ts, prices):
        for leg in roll_legs:
            if leg["qty"] <= 0:
                continue
            if leg["oid"] is not None:
                if not cancel(leg["oid"]):
                    continue                  # still live (e.g. cancel refused in the ATC)
                roll_by_oid.pop(leg["oid"], None)
                leg["oid"] = None
            send_leg(leg, ts, prices.get(leg["ticker"]))

    # ---- naive's loop, verbatim control flow ----------------------------
    expiration_dates = get_expired_dates(data["datetime"].iloc[0], data["datetime"].iloc[-1])
    cur_index = 0
    moving_to_f2 = False
    last_timed: Optional[datetime] = None
    equity = [float(A.DEPOSIT_DONG)]
    dates_all = data["date"].tolist()
    n = len(data)
    t0 = _time.time()
    cols = data[["datetime", "date", "price", "f2_price", "tickersymbol", "f2-tickersymbol"]]
    charges_prev = Decimal(0)
    for i, (dt, d, p1, p2, tk1, tk2) in enumerate(cols.itertuples(index=False, name=None)):
        if d not in run_set:
            break
        ts = dt.to_pydatetime()
        quote_filled = absorb(backend.advance_to(ts))
        last_px[tk1] = p1
        last_px[tk2] = p2
        if (cur_index != len(trading_dates) - 1 and not expiration_dates.empty()
                and trading_dates[cur_index + 1] >= expiration_dates.queue[0]):
            expiration_dates.get()
            moving_to_f2 = True
            q = pos.get(tk1, 0)
            s["roll_triggers"] += 1
            if q != 0:
                s["roll_contracts"] += abs(q)
                new_leg(tk1, Side.SELL if q > 0 else Side.BUY, abs(q), ts, p1)
                new_leg(tk2, Side.BUY if q > 0 else Side.SELL, abs(q), ts, p2)
        ticker = tk2 if moving_to_f2 else tk1
        price = p2 if moving_to_f2 else p1
        if last_timed is None or ts > last_timed + A.REQUOTE:
            last_timed = ts
            if any(leg["qty"] > 0 for leg in roll_legs):
                retry_rolls(ts, {tk1: p1, tk2: p2})
            requote(ticker, price)
        elif quote_filled:
            requote(ticker, price)

        if i == n - 1 or dates_all[i + 1] != d:
            # day end: through the ATC to the close; settlement runs there
            absorb(backend.advance_to(datetime.combine(d, time(14, 44, 59))))
            absorb(backend.advance_to(datetime.combine(d, DAY_END)))
            live_quotes.clear()
            for leg in roll_legs:
                s["roll_unfilled_contracts"] += max(leg["qty"], 0)
            roll_legs.clear()
            roll_by_oid.clear()
            charges = sum((c.total for c in backend.charges()), Decimal(0))
            mtm = Decimal(0)
            for c, q in pos.items():
                if q:
                    mark = close_of.get((d, c), last_px.get(c))
                    mtm += q * mark * A.MULT
            eq = Decimal(A.DEPOSIT_DONG) + cash + mtm - charges
            equity.append(float(eq))
            mv = backend.margin()
            engine_pos = {c: p.net_quantity for c, p in backend.positions().items()}
            mine = {c: q for c, q in pos.items() if q}
            rec = {"date": d.isoformat(), "contract": ticker, "rolled": moving_to_f2,
                   **{k: int(v) for k, v in s.items()},
                   "end_net": net(), "positions": mine,
                   "positions_match_engine": engine_pos == mine,
                   "charges_dong": float(charges - charges_prev),
                   "end_equity_dong": float(eq),
                   "engine_deposit_dong": float(mv.deposit_balance),
                   "engine_margin_status": getattr(mv.status, "value", str(mv.status))}
            charges_prev = charges
            per_session.append(rec)
            tot.update(s)
            log(f"  [{queue}] {d} {ticker} fills={s['fills']} net={net()} eq={float(eq):,.0f} "
                f"dep={float(mv.deposit_balance):,.0f} ind={s['indeterminate_orders']}/"
                f"{s['quote_submitted']} calls={s['margin_call']} ({_time.time() - t0:.0f}s)")
            s = Counter()
            cur_index += 1
            moving_to_f2 = False
            last_timed = None

    entries = sess._derivatives.entries   # read-only: VM settlement audit
    vm = [e for e in entries if "variation-margin settlement" in e.reason]
    ign = backend.indeterminate_report()
    out = {
        "window": window, "queue": queue, "step": str(step),
        "sessions": len(per_session),
        "rows": n,
        "plutus_simulator_commit": commit_at_start,
        "plutus_simulator_src_dirty": dirty_at_start,
        "plutus_simulator_commit_at_end": A._engine_commit(),
        "equity_dong": equity,
        "totals": {k: int(v) for k, v in tot.items()},
        "refusals": dict(refusals),
        "vm_settlements": {"count": len(vm),
                           "net_dong": float(sum((e.amount for e in vm), Decimal(0))),
                           "first": vm[0].ts.isoformat() if vm else None},
        "margin_events": margin_events,
        "engine_ignorance": {"evaluations": ign.evaluations,
                             "indeterminate": ign.indeterminate,
                             "silent_ignorance": dict(getattr(ign, "silent_ignorance", {}) or {})},
        "final_engine_deposit_dong": float(backend.margin().deposit_balance),
        "per_session": per_session,
        "wall_seconds": round(_time.time() - t0, 1),
    }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("window", choices=sorted(WINDOWS))
    ap.add_argument("--queue", choices=("optimistic", "conservative"), required=True)
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    out = run_faithful_a(args.window, args.queue, max_sessions=args.max_sessions)
    path = args.out or (A.REPO / "result" / "mm_faithful_a" / f"{args.window}_{args.queue}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
