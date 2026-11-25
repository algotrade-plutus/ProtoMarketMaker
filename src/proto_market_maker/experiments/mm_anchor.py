"""Naive vs faithful ProtoMarketMaker on one frozen L2 window (RIVF'26, T5).

Both arms replay the **same** pure signal :func:`proto_market_maker.strategy.quote`
at ``step = 3.1`` (``parameter/optimized_parameter.json``) over the **same**
frozen slice (``data/l2/<window>``, ``data/band/<window>``,
``data/market/<window>``). The only difference is execution.

Naive arm
    The repository's own engine, ``backtest.Backtesting``, unchanged except that
    its quoting lines call ``strategy.quote``. A quote fills whenever the last
    trade price crosses it; capacity is a flat 17% margin on cash; inventory is
    carried overnight. Its units are thousands of dong with a multiplier of 100
    per point; they are converted to real dong (x1000) on output.

Faithful arm (``plutus.execution.PlutusBackend`` over an ``ExchangeSession``)
    * Real dong: a derivatives deposit of **500,000,000 dong** on the first
      session, the real VN30F multiplier **100,000 dong/point** (resolved by
      the engine per contract).
    * Dated VSD initial margin: the session margins each order through
      ``plutus.market.session.deposit.resolve_initial_margin_rate``, which falls
      back to ``plutus.market.margin.vsd_initial_margin`` (13% before
      2022-12-15, 17% from it). The runner reads the same function for the
      contract-capacity counter.
    * Fills: ``book_walk`` over the L2 depth (levels 1-3) and the sized tape.
      ``conservative`` is the headline queue, ``optimistic`` the bound; the
      queue spread is reported relative to the optimistic arm. A third arm,
      ``conservative_untaped``, injects a conservative queue whose taker walk
      gets no prints: it reproduces the engine before plutus-simulator
      ``e528633`` (taker sweeps undecidable), so the before/after of that
      engine change is measured on the same run.
    * Cadence: on every trade print of the traded contract between 09:00 and
      14:25 the clock is advanced to it; the quotes are cancelled and replaced
      (a derivatives order cannot be amended) when 15 s have passed since the
      last timed requote, or right after a fill -- the naive engine's own rule.
      Each quote is one contract.
    * Each session is closed out: quoting stops at 14:25; a residual position
      is offered through the touch (a marketable LIMIT one point through the
      opposite best, re-priced every 15 s) until 14:29:59. Whatever the engine
      does not fill is marked at that day's close price by this harness and
      counted (``closeout_marked_contracts``). Every session opens flat with the
      previous session's ending equity as its deposit.
    * Regime guard (the S6 rule): before each session the strategy asks the
      dated rulebook for the margin model and quotes only under a model it
      knows (``KNOWN_MARGIN_MODELS``: ``pre_margin``, and ``krx_two_layer`` from
      the 2025-05-05 KRX cutover, sourced in plutus-simulator ``391e2e2``); an
      unresolved or unknown model refuses the session rather than invent a
      margin rule. Before ``391e2e2`` the post-KRX model was unsourced and the
      guard refused all 20 post-cutover sessions; it no longer refuses any.
      ``--unguarded`` skips the check.

The contract traded each day is the naive engine's: VN30F1M, or VN30F2M on the
session before the front month's expiry (``windows.traded_contracts``).

Proceed gate (pre-registered, activity/credibility only): the naive arm
completes >= 300 round trips over the two windows; the faithful arm completes
without an unbounded margin-liquidation cascade (forced liquidations <= sessions).
No Sharpe/HPR gate. See ``tests/test_proceed_gate.py``.

Run::

    .venv/bin/python -m proto_market_maker.experiments.mm_anchor krx2025
    .venv/bin/python -m proto_market_maker.experiments.mm_anchor im2022

Writes ``result/mm_anchor/<window>.json``.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time as _time
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from proto_market_maker.experiments.windows import (WINDOWS, roll_days,
                                                     traded_contracts)
from proto_market_maker.strategy import quote

REPO = Path(__file__).resolve().parents[3]
SIM_ROOT = Path(os.environ.get("PLUTUS_SIM_ROOT", REPO.parents[1] / "plutus-simulator"))
DEPOSIT_DONG = 500_000_000
MULT = 100_000                       # dong per index point (real VN30F)
NAIVE_SCALE = 1000                   # naive engine units are thousand dong
RF_DAILY = 0.00023
REQUOTE = timedelta(seconds=15)
QUOTE_FROM, QUOTE_TO = time(9, 0), time(14, 25)
CLOSE_TO = time(14, 29, 59)
CLOSEOUT_THROUGH = Decimal("1.0")    # points through the opposite touch
KRX_CUTOVER = date(2025, 5, 5)
IM_STEP = date(2022, 12, 15)
QUEUES = ("conservative", "optimistic", "conservative_untaped")


def _roots(window: str):
    l2 = os.environ.get("PLUTUS_DEPTH_ROOT") or str(REPO / "data" / "l2" / window)
    band = os.environ.get("PLUTUS_DATA_ROOT") or str(REPO / "data" / "band" / window)
    return band, l2


def step_param() -> Decimal:
    with open(REPO / "parameter" / "optimized_parameter.json", encoding="utf-8") as f:
        return Decimal(str(json.load(f)["step"]))


def load_contract_map(window: str):
    fcc, days = {}, set()
    with open(REPO / "data" / "market" / window / "futurecontractcode.csv",
              encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            d = date.fromisoformat(row["datetime"])
            fcc[(d, row["futurecode"])] = row["tickersymbol"]
            days.add(d)
    return fcc, sorted(days)


def _engine_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(SIM_ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # pragma: no cover
        return "unknown"


def _engine_dirty() -> bool:
    try:
        out = subprocess.run(["git", "-C", str(SIM_ROOT), "status", "--porcelain",
                              "--", "src"], capture_output=True, text=True,
                             check=True).stdout
        return bool(out.strip())
    except Exception:  # pragma: no cover
        return True


# --------------------------------------------------------------------------
# metrics (the naive engine's own definitions)
# --------------------------------------------------------------------------

def _metrics(equity: List[float]) -> dict:
    rets = [equity[i] / equity[i - 1] - 1.0 for i in range(1, len(equity))]
    hpr = equity[-1] / equity[0] - 1.0
    sharpe = None
    if len(rets) > 1 and np.std(rets, ddof=1) > 0:
        sharpe = float((np.mean(rets) - RF_DAILY) / np.std(rets, ddof=1) * math.sqrt(250))
    peak, mdd = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return {"hpr": hpr, "sharpe": sharpe, "mdd": mdd,
            "start_equity_dong": equity[0], "end_equity_dong": equity[-1]}


# --------------------------------------------------------------------------
# naive arm
# --------------------------------------------------------------------------

def _naive_frames(window: str, sessions: List[date], fcc):
    _, l2 = _roots(window)
    band, _ = _roots(window)
    matched = pd.read_parquet(Path(l2) / "local_quote_matched.parquet")
    bid = pd.read_parquet(Path(l2) / "local_quote_bidprice.parquet")
    ask = pd.read_parquet(Path(l2) / "local_quote_askprice.parquet")
    close = pd.read_parquet(Path(band) / "quote_close.parquet")
    close = close.rename(columns={"datetime": "date", "price": "close"})
    close["date"] = pd.to_datetime(close["date"]).dt.date

    def hours(df):
        t = df["datetime"].dt
        return df[((t.hour >= 9) & (t.hour < 14)) | ((t.hour == 14) & (t.minute <= 30))]

    def frame(code: str, with_book: bool):
        keep = {(d, fcc[(d, code)]) for d in sessions}
        def sel(df):
            df = df.copy()
            df["date"] = df["datetime"].dt.date
            mask = [(d, t) in keep for d, t in zip(df["date"], df["tickersymbol"])]
            return hours(df[mask]).drop(columns="date")
        m = sel(matched)[["datetime", "tickersymbol", "price"]]
        m["price"] = m["price"].astype(float)
        if with_book:
            b = sel(bid[bid["depth"] == 1])[["datetime", "tickersymbol", "price"]]
            a = sel(ask[ask["depth"] == 1])[["datetime", "tickersymbol", "price"]]
            ba = b.merge(a, on=["datetime", "tickersymbol"], suffixes=("_b", "_a"))
            ba["best-bid"] = ba["price_b"].astype(float)
            ba["best-ask"] = ba["price_a"].astype(float)
            ba["spread"] = ba["best-ask"] - ba["best-bid"]
            ba = ba[["datetime", "tickersymbol", "best-bid", "best-ask", "spread"]]
            data = m.merge(ba, on=["datetime", "tickersymbol"], how="outer", sort=True)
        else:
            data = m.sort_values("datetime")
        data = data.ffill()
        data["date"] = data["datetime"].dt.date
        data = data.merge(close, on=["date", "tickersymbol"], how="inner", sort=True)
        data["close"] = data["close"].astype(float)
        data = data.dropna(subset=["price"]).reset_index(drop=True)
        data["datetime"] = data["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        data["date"] = data["date"].astype(str)
        return data

    return frame("VN30F1M", True), frame("VN30F2M", False)


def run_naive(window: str, sessions: List[date], fcc, step: Decimal) -> dict:
    from proto_market_maker.backtest import Backtesting

    class Counted(Backtesting):
        fills = 0
        closing_fills = 0
        forced_reductions = 0

        def handle_matched_order(self, price):
            before = self.inventory
            m = super().handle_matched_order(price)
            if self.inventory != before:
                self.fills += abs(self.inventory - before)
                if abs(self.inventory) < abs(before):
                    self.closing_fills += 1
            return m

        def handle_force_sell(self, price):
            before = self.inventory
            super().handle_force_sell(price)
            self.forced_reductions += abs(before - self.inventory)

    f1, f2 = _naive_frames(window, sessions, fcc)
    data = Backtesting.prepare(f1, f2)
    # The outer merge leaves F2M fields empty until F2M's first print; the
    # engine cannot price those rows (im2022 opens on an expiry/roll session),
    # so the stream starts at the first row carrying both prices.
    first = data[data["f2_price"].notna() & data["price"].notna()].index[0]
    data = data.loc[first:].reset_index(drop=True)
    bt = Counted(capital=Decimal("5e5"), printable=False)
    bt.run(data, step)
    equity = [float(a) * NAIVE_SCALE for a in bt.daily_assets]
    out = _metrics(equity)
    out.update({
        "fills": bt.fills,
        "round_trips": bt.closing_fills,
        "forced_reductions": bt.forced_reductions,
        "sessions": len(bt.daily_returns),
        "end_inventory": bt.inventory,
        "units": "real dong (naive engine thousand-dong x 1000; multiplier 100 = 100,000 dong/pt / 1000)",
        "margin_rate": "flat 0.17 (from_cash_to_tradeable_contracts)",
        "carries_inventory_overnight": True,
        "rows": len(data),
    })
    return out


# --------------------------------------------------------------------------
# faithful arm
# --------------------------------------------------------------------------

def _untaped_conservative():
    from plutus.market.session.book_walk import ConservativeQueue

    class UntapedConservative(ConservativeQueue):
        """Pre-e528633 behaviour: the taker walk gets no prints (a subclass, so
        ``BookWalkFillPolicy`` does not swap in the tape-fed queue)."""

        @property
        def signature(self) -> str:
            return "conservative(prints=absent)"

    return UntapedConservative()


def _session(day: date, deposit: int, queue: str, source):
    from plutus.market.session import ExchangeSession, parse_config
    from plutus.market.session.book_walk import BookWalkFillPolicy
    from plutus.execution import PlutusBackend

    kind = "conservative" if queue == "conservative_untaped" else queue
    config = parse_config({
        "period": {"start": day.isoformat(),
                   "end": (day + timedelta(days=1)).isoformat()},
        "resolution": "tick",
        "exchange_rules": {"venues": ["HNXDS"]},
        "accounts": {"derivatives": {"initial_deposit": deposit,
                                     "account_no": "DER-MM"}},
        "fill_policy": {"kind": "book_walk", "queue": kind,
                        "max_participation": None, "max_staleness": None},
    })
    policy = None
    if queue == "conservative_untaped":
        policy = BookWalkFillPolicy(source, queue=_untaped_conservative(),
                                    max_participation=None, max_staleness=None,
                                    tape=source)
    return PlutusBackend(ExchangeSession.build(config, source=source,
                                               fill_policy=policy))


def _kind(e) -> str:
    return getattr(getattr(e, "kind", None), "value", getattr(e, "kind", ""))


#: The dated margin models this strategy knows how to be margined under
#: (plutus-simulator ``391e2e2``): ``pre_margin`` before the 2025-05-05 KRX
#: cutover, ``krx_two_layer`` (QD 26: broker IM intraday, VSDC CCP after the
#: close) from it. Anything else, or an unresolved rule, is refused.
KNOWN_MARGIN_MODELS = frozenset({"pre_margin", "krx_two_layer"})


def _margin_model_ok(day: date) -> bool:
    from plutus.market.session.rulebook import Rulebook, UnresolvedRule
    try:
        model = Rulebook().at(datetime.combine(day, time(9, 0))).margin_model()
    except UnresolvedRule:
        return False
    return model in KNOWN_MARGIN_MODELS


def _capacity(deposit: float, price: float, day: date) -> dict:
    from plutus.market.margin import vsd_initial_margin
    rate = vsd_initial_margin(day)
    return {"rate": str(rate),
            "contracts": int(Decimal(str(deposit)) // (Decimal(str(price)) * MULT * rate))}


def run_faithful(window: str, sessions: List[date], fcc, step: Decimal,
                 queue: str, guard: bool = True, days: Optional[List[date]] = None,
                 log=print) -> dict:
    from plutus.market.adapters.book_session import BookSessionSource
    from plutus.market.protocol import Order
    from plutus.core.order import OrderType, Side
    from plutus.market.session import Accepted

    band, l2 = _roots(window)
    source = BookSessionSource.for_roots(band, l2)
    traded = traded_contracts(sessions, fcc)
    matched = pd.read_parquet(Path(l2) / "local_quote_matched.parquet")
    closes = pd.read_parquet(Path(band) / "quote_close.parquet")
    close_of = {(pd.Timestamp(d).date(), t): float(p)
                for d, t, p in zip(closes["datetime"], closes["tickersymbol"], closes["price"])}

    equity = [float(DEPOSIT_DONG)]
    eq_dates: List[str] = []
    tot = Counter()
    refusals, ind_fields, ind_arm = Counter(), Counter(), Counter()
    per_session = []
    capacity = []

    for day in (days or sessions):
        ticker = traded[day]
        deposit = int(equity[-1])
        rec = {"date": day.isoformat(), "contract": ticker}
        ticks = matched[(matched["tickersymbol"] == ticker)
                        & (matched["datetime"].dt.date == day)]
        ticks = ticks[(ticks["datetime"].dt.time >= QUOTE_FROM)
                      & (ticks["datetime"].dt.time <= CLOSE_TO)]
        first_price = float(ticks["price"].iloc[0]) if len(ticks) else None
        if first_price is not None:
            capacity.append({"date": day.isoformat(), "deposit_dong": deposit,
                             "price": first_price, **_capacity(deposit, first_price, day)})

        if guard and not _margin_model_ok(day):
            tot["refused_sessions"] += 1
            rec["refused"] = "margin_model unresolved or not a known model"
            per_session.append(rec)
            equity.append(equity[-1]); eq_dates.append(day.isoformat())
            continue

        backend = _session(day, deposit, queue, source)
        live: Dict[str, Side] = {}
        closer: Optional[str] = None
        cash = Decimal(0)
        net = 0
        last_timed: Optional[datetime] = None
        counted_ind_orders = set()
        s = Counter()

        def submit(side, price) -> Optional[str]:
            ack = backend.submit(Order(ticker=ticker, side=side, quantity=1,
                                       order_type=OrderType.LIMIT, limit_price=price))
            s["submitted"] += 1
            if isinstance(ack, Accepted):
                return ack.order_id
            rule = getattr(ack.rule, "name", str(ack.rule))
            verdict = getattr(ack.verdict, "value", str(ack.verdict))
            refusals[f"{rule}:{verdict}"] += 1
            s["rejected"] += 1
            return None

        def cancel_all():
            nonlocal closer
            for oid in list(live):
                backend.cancel(oid)
            live.clear()
            if closer is not None:
                backend.cancel(closer)
                closer = None

        def absorb(events) -> bool:
            nonlocal cash, net
            filled = False
            for e in events:
                k = _kind(e)
                if k in ("filled", "partially_filled"):
                    side = live.get(e.order_id)
                    if side is None and e.order_id == closer:
                        side = Side.SELL if net > 0 else Side.BUY
                        s["closeout_fills"] += e.quantity
                    if side is None:
                        continue
                    q = int(e.quantity)
                    px = Decimal(str(e.price))
                    if side is Side.BUY:
                        cash -= px * q * MULT; net += q
                    else:
                        cash += px * q * MULT; net -= q
                    s["fills"] += q
                    s["maker_fills" if e.detail.get("maker") else "taker_fills"] += q
                    filled = True
                    if e.order_id in live and k == "filled":
                        live.pop(e.order_id, None)
                elif k == "indeterminate":
                    reason = str(e.detail.get("reason", ""))
                    arm = "maker" if " maker " in reason else "taker"
                    ind_arm[arm] += 1
                    s["indeterminate_evals"] += 1
                    for f in (e.detail.get("missing") or ()):
                        ind_fields[getattr(f, "value", str(f))] += 1
                    if e.order_id not in counted_ind_orders:
                        counted_ind_orders.add(e.order_id)
                        s["indeterminate_orders"] += 1
                elif k == "margin_call":
                    s["margin_calls"] += 1
                elif k == "forced_liquidation":
                    s["forced_liquidations"] += 1
            return filled

        def requote(ts, price):
            cancel_all()
            bid, ask = quote(price, net, step)
            for side, px in ((Side.BUY, bid), (Side.SELL, ask)):
                oid = submit(side, px)
                if oid is not None:
                    live[oid] = side

        for ts, price in zip(ticks["datetime"], ticks["price"]):
            ts = ts.to_pydatetime()
            price = Decimal(str(price)).quantize(Decimal("0.1"))
            filled = absorb(backend.advance_to(ts))
            if ts.time() <= QUOTE_TO:
                if last_timed is None or ts > last_timed + REQUOTE:
                    last_timed = ts
                    requote(ts, price)
                elif filled:
                    requote(ts, price)
            else:
                # close-out: stop quoting, offer the residual through the touch
                if live:
                    cancel_all()
                if net != 0 and (closer is None or filled or ts > last_timed + REQUOTE):
                    if closer is not None:
                        backend.cancel(closer); closer = None
                    book = source.book_at(ticker, ts)
                    side = Side.SELL if net > 0 else Side.BUY
                    touch = (book.bid.best if side is Side.SELL else book.ask.best)
                    if touch is not None:
                        px = (touch.price - CLOSEOUT_THROUGH if side is Side.SELL
                              else touch.price + CLOSEOUT_THROUGH)
                        ack = backend.submit(Order(ticker=ticker, side=side,
                                                   quantity=abs(net),
                                                   order_type=OrderType.LIMIT,
                                                   limit_price=px.quantize(Decimal("0.1"))))
                        s["closeout_orders"] += 1
                        if isinstance(ack, Accepted):
                            closer = ack.order_id
                        else:
                            refusals[f"closeout:{getattr(ack.rule, 'name', ack.rule)}"] += 1
                    last_timed = ts
                elif net == 0 and closer is not None:
                    backend.cancel(closer); closer = None
        if len(ticks):
            absorb(backend.advance_to(datetime.combine(day, CLOSE_TO)))
        cancel_all()
        charges = sum((c.total for c in backend.charges()), Decimal(0))
        close_px = close_of.get((day, ticker))
        if net != 0:
            s["closeout_marked_contracts"] += abs(net)
            mark = Decimal(str(close_px if close_px is not None else ticks["price"].iloc[-1]))
            cash += mark * net * MULT
        ign = backend.indeterminate_report()
        s["evaluations"] = ign.evaluations
        s["engine_indeterminate"] = ign.indeterminate
        pnl = cash - charges
        equity.append(float(Decimal(deposit) + pnl))
        eq_dates.append(day.isoformat())
        rec.update({k: int(v) for k, v in s.items()})
        rec.update({"pnl_dong": float(pnl), "charges_dong": float(charges),
                    "end_equity_dong": equity[-1]})
        per_session.append(rec)
        tot.update(s)
        log(f"  [{queue}] {day} {ticker} fills={s['fills']} eq={equity[-1]:,.0f} ind_orders="
            f"{s['indeterminate_orders']}/{s['submitted']} marked={s['closeout_marked_contracts']}")

    def rate(a, b):
        return (a / b) if b else None

    def split(pred):
        sub = [r for r in per_session if pred(date.fromisoformat(r["date"]))]
        c = Counter()
        for r in sub:
            c.update({k: v for k, v in r.items() if isinstance(v, int)})
        return {"sessions": len(sub), "refused_sessions": sum(1 for r in sub if "refused" in r),
                "fills": c["fills"], "submitted": c["submitted"],
                "indeterminate_orders": c["indeterminate_orders"],
                "indeterminate_order_rate": rate(c["indeterminate_orders"], c["submitted"] - c["rejected"]),
                "evaluations": c["evaluations"], "engine_indeterminate": c["engine_indeterminate"],
                "indeterminate_eval_rate": rate(c["engine_indeterminate"], c["evaluations"])}

    out = _metrics(equity)
    accepted = tot["submitted"] - tot["rejected"]
    out.update({
        "queue": queue,
        "guard": guard,
        "fills": tot["fills"],
        "maker_fills": tot["maker_fills"],
        "taker_fills": tot["taker_fills"],
        "closeout_fills": tot["closeout_fills"],
        "closeout_marked_contracts": tot["closeout_marked_contracts"],
        "submitted": tot["submitted"],
        "accepted": accepted,
        "refusals": dict(refusals),
        "refused_sessions": tot["refused_sessions"],
        "indeterminate": {
            "orders": tot["indeterminate_orders"],
            "order_rate": rate(tot["indeterminate_orders"], accepted),
            "fill_events": tot["indeterminate_evals"],
            "by_arm": dict(ind_arm),
            "by_field": dict(ind_fields),
            "engine_evaluations": tot["evaluations"],
            "engine_indeterminate": tot["engine_indeterminate"],
            "engine_rate": rate(tot["engine_indeterminate"], tot["evaluations"]),
        },
        "margin_calls": tot["margin_calls"],
        "forced_liquidations": tot["forced_liquidations"],
        "sessions": len(per_session),
        "deposit_dong": DEPOSIT_DONG,
        "multiplier_dong_per_point": MULT,
        "capacity": capacity,
        "per_session": per_session,
    })
    if window == "krx2025":
        out["krx"] = {"pre": split(lambda d: d < KRX_CUTOVER),
                      "post": split(lambda d: d >= KRX_CUTOVER)}
    if window == "im2022":
        out["im_step"] = {"pre": split(lambda d: d < IM_STEP),
                          "post": split(lambda d: d >= IM_STEP)}
    return out


def dated_margin_probe(window: str, sessions: List[date], fcc) -> dict:
    """Contracts 500,000,000 dong affords at the 13% and 17% VSD IM, at one price.

    The price is the traded contract's close on the last session before the
    2022-12-15 step (im2022) or the first session of the window (krx2025), so
    the only thing that changes is the dated ratio."""
    band, _ = _roots(window)
    closes = pd.read_parquet(Path(band) / "quote_close.parquet")
    traded = traded_contracts(sessions, fcc)
    pre = [d for d in sessions if d < IM_STEP]
    day = pre[-1] if pre else sessions[0]
    row = closes[(pd.to_datetime(closes["datetime"]).dt.date == day)
                 & (closes["tickersymbol"] == traded[day])]
    price = float(row["price"].iloc[0])
    before = _capacity(DEPOSIT_DONG, price, date(2022, 12, 14))
    after = _capacity(DEPOSIT_DONG, price, date(2022, 12, 15))
    return {"price_date": day.isoformat(), "contract": traded[day], "price": price,
            "deposit_dong": DEPOSIT_DONG, "at_13pct": before, "at_17pct": after,
            "cut_contracts": before["contracts"] - after["contracts"]}


def run_mm_anchor(window: str, queues=QUEUES, unguarded_diag: bool = True,
                  log=print) -> dict:
    fcc, sessions = load_contract_map(window)
    step = step_param()
    t0 = _time.time()
    naive = run_naive(window, sessions, fcc, step)
    getattr(log, "note", log)(f"naive: fills={naive['fills']} round_trips={naive['round_trips']} "
                              f"hpr={naive['hpr']:.4f}")
    arms = {q: run_faithful(window, sessions, fcc, step, q, log=log) for q in queues}
    faithful = arms["conservative"]
    opt = arms.get("optimistic")
    spread = {q: a["fills"] for q, a in arms.items()}
    if opt and opt["fills"]:
        spread["conservative_vs_optimistic_pct"] = (
            (opt["fills"] - faithful["fills"]) / opt["fills"] * 100.0)
    diag = None
    if unguarded_diag and window == "krx2025":
        post = [d for d in sessions if d >= KRX_CUTOVER]
        diag = {q: run_faithful(window, sessions, fcc, step, q, guard=False,
                                days=post, log=log)
                for q in ("conservative", "optimistic")}
        for d in diag.values():
            d.pop("per_session", None)
    naive_pre = None
    if window == "krx2025":
        # Like-for-like span: the faithful arm quotes only pre-cutover sessions
        # (the regime guard refuses the rest), so the naive arm is also run on
        # those sessions alone.
        naive_pre = run_naive(window, [d for d in sessions if d < KRX_CUTOVER],
                              fcc, step)
    tier1 = {
        "queue_fill_spread": spread,
        "indeterminate_rate_by_queue": {
            q: {"order_rate": a["indeterminate"]["order_rate"],
                "engine_eval_rate": a["indeterminate"]["engine_rate"],
                "taker_fills": a["taker_fills"], "maker_fills": a["maker_fills"],
                "by_arm": a["indeterminate"]["by_arm"]}
            for q, a in arms.items()},
        "dated_margin": dated_margin_probe(window, sessions, fcc),
        "margin_calls": faithful["margin_calls"],
        "forced_liquidations": faithful["forced_liquidations"],
        "refusals": faithful["refusals"],
        "post_cutover_refused_sessions": faithful["refused_sessions"],
    }
    return {
        "window": window,
        "sessions": [d.isoformat() for d in sessions],
        "roll_days": [d.isoformat() for d in roll_days(sessions)],
        "step": str(step),
        "plutus_simulator_commit": _engine_commit(),
        "plutus_simulator_src_dirty": _engine_dirty(),
        "naive": naive,
        "naive_pre_cutover_only": naive_pre,
        "faithful": faithful,
        "faithful_by_queue": {q: a for q, a in arms.items() if q != "conservative"},
        "post_cutover_unguarded_diagnostic": diag,
        "tier1": tier1,
        "fills_ratio_f_over_n": (faithful["fills"] / naive["fills"]) if naive["fills"] else None,
        "wall_seconds": round(_time.time() - t0, 1),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("window", choices=sorted(WINDOWS))
    ap.add_argument("--queues", default=",".join(QUEUES))
    ap.add_argument("--no-diag", action="store_true")
    ap.add_argument("--log", type=Path, default=None,
                    help="progress log file: one flushed line per faithful session, with ETA")
    args = ap.parse_args(argv)
    from proto_market_maker.experiments.mm_fills_trace import ProgressLog
    queues = tuple(args.queues.split(","))
    _, sessions = load_contract_map(args.window)
    post = [d for d in sessions if d >= KRX_CUTOVER]
    total = len(sessions) * len(queues) + (
        2 * len(post) if args.window == "krx2025" and not args.no_diag else 0)
    plog = ProgressLog(args.log, total, f"mm_anchor {args.window}")
    plog.note(f"plutus-simulator commit at start: {_engine_commit()}")
    out = run_mm_anchor(args.window, queues, unguarded_diag=not args.no_diag, log=plog)
    path = REPO / "result" / "mm_anchor" / f"{args.window}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=str) + "\n")
    plog.note(f"wrote {path}")
    plog.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
