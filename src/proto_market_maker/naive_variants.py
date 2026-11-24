"""Naive-engine variants for the RIVF'26 MarketMaker attribution ladder.

``backtest.Backtesting`` is left untouched; every rung is an opt-in option on
this subclass, so the default naive output stays byte-identical. Pure: no
plutus import (the dated IM rule is implemented locally, below).

Rungs (cumulative in ``experiments/mm_ladder.py``, independent flags here):

1. ``aligned`` -- close the design mismatches with the faithful arm:
   quote only 09:00 <= t < 14:25:00 on the traded contract's own prints (no
   F1/F2 outer-merge / forward fill, no synthetic F1->F2 roll); at the first
   print at or after 14:25:00 cancel the quotes and close any residual position
   at that print. A residual that sees no such print is marked at the day's
   close (counted in ``marked_contracts``). No inventory is carried overnight.
2. ``own_price_fills`` -- a crossed quote books at its own price (the bid or
   the ask), not at the print that crossed it.
3. ``dated_im`` -- contract capacity at the dated VSD initial-margin rate
   (13% before 2022-12-15, 17% from it) instead of the flat 17%.
4. ``fee_every_fill`` -- ``FEE_PER_CONTRACT`` on every fill, not only on
   position-reducing ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Tuple

from proto_market_maker.backtest import Backtesting, FEE_PER_CONTRACT
from proto_market_maker.metrics.metric import Metric
from proto_market_maker.utils import from_cash_to_tradeable_contracts

QUOTE_FROM = time(9, 0)
QUOTE_TO = time(14, 25)          # quoting stops at 14:25:00; close-out at first print >= it
CLOSE_TO = time(14, 29, 59)      # last print considered (same as the faithful arm)

# VSD (Vietnam Securities Depository) raised the VN30F initial-margin rate
# from 13% to 17% effective 2022-12-15. Same rule as
# plutus.market.margin.vsd_initial_margin, re-implemented here so the naive
# engine stays free of plutus imports.
VSD_IM_STEP = date(2022, 12, 15)
VSD_IM_BEFORE = Decimal("0.13")
VSD_IM_FROM = Decimal("0.17")


def vsd_initial_margin_rate(day: date) -> Decimal:
    """Dated VSD initial-margin rate for VN30F (VSD, effective 2022-12-15)."""
    if isinstance(day, datetime):
        day = day.date()
    return VSD_IM_FROM if day >= VSD_IM_STEP else VSD_IM_BEFORE


@dataclass(frozen=True)
class NaiveOptions:
    aligned: bool = False
    own_price_fills: bool = False
    dated_im: bool = False
    fee_every_fill: bool = False

    @classmethod
    def rung(cls, n: int) -> "NaiveOptions":
        """Cumulative ladder rung 0..4 (0 = the naive engine as-is)."""
        if not 0 <= n <= 4:
            raise ValueError(n)
        return cls(aligned=n >= 1, own_price_fills=n >= 2,
                   dated_im=n >= 3, fee_every_fill=n >= 4)


# one session: (day, traded contract, [(timestamp, price)], close price)
Session = Tuple[date, str, Sequence[Tuple[datetime, Decimal]], Optional[Decimal]]


class NaiveVariant(Backtesting):
    """``Backtesting`` with the ladder options. With all options off it is the
    base engine (``run`` is inherited; the fill rule below reduces to the base
    rule) plus fill counters."""

    def __init__(self, capital: Decimal, options: NaiveOptions = NaiveOptions(),
                 printable: bool = False):
        super().__init__(capital, printable=printable)
        self.options = options
        self.cur_date = None
        self.fills = 0              # contracts filled (quotes + close-out)
        self.closing_fills = 0      # position-reducing contracts (= round trips)
        self.forced_reductions = 0
        self.closeout_contracts = 0
        self.marked_contracts = 0
        self.fees_charged = Decimal("0")   # thousand dong, for reporting

    # ---- rung 3: dated IM ------------------------------------------------
    def get_maximum_placeable(self, inst_price: Decimal):
        if not self.options.dated_im:
            return super().get_maximum_placeable(inst_price)
        total = max(from_cash_to_tradeable_contracts(
            self.daily_assets[-1] - self.ac_loss, inst_price,
            margin_rate=vsd_initial_margin_rate(self.cur_date)), 0)
        return total - abs(self.inventory)

    def handle_force_sell(self, price: Decimal):
        before = self.inventory
        super().handle_force_sell(price)
        self.forced_reductions += abs(before - self.inventory)

    # ---- rungs 2 and 4: fill price and fee -------------------------------
    def handle_matched_order(self, price):
        """The base rule, verbatim, with the booked price and the opening fee
        made optional. Options off: identical to ``Backtesting``."""
        matched = 0
        placeable = self.get_maximum_placeable(price)
        if self.bid_price is None or self.ask_price is None:
            return matched
        own = self.options.own_price_fills
        buy_px = self.bid_price if own else price
        sell_px = self.ask_price if own else price
        open_fee = FEE_PER_CONTRACT if self.options.fee_every_fill else Decimal("0")

        if self.bid_price >= price and self.inventory >= 0 and placeable > 0:
            self.inventory_price = (
                self.inventory_price * abs(self.inventory) + buy_px
            ) / (abs(self.inventory) + 1)
            self.inventory += 1
            matched += 1
            if open_fee:
                self.ac_loss += open_fee
                self.fees_charged += open_fee
            self.fills += 1
        elif self.bid_price >= price and self.inventory < 0:
            self.ac_loss += (FEE_PER_CONTRACT - (self.inventory_price - buy_px) * Decimal('100'))
            self.fees_charged += FEE_PER_CONTRACT
            self.inventory += 1
            matched -= 1
            self.fills += 1
            self.closing_fills += 1

        if self.ask_price <= price and self.inventory <= 0 and placeable > 0:
            self.inventory_price = (
                self.inventory_price * abs(self.inventory) + sell_px
            ) / (abs(self.inventory) + 1)
            self.inventory -= 1
            matched += 1
            if open_fee:
                self.ac_loss += open_fee
                self.fees_charged += open_fee
            self.fills += 1
        elif self.ask_price <= price and self.inventory > 0:
            self.ac_loss += (FEE_PER_CONTRACT - (sell_px - self.inventory_price) * Decimal('100'))
            self.fees_charged += FEE_PER_CONTRACT
            self.inventory -= 1
            matched -= 1
            self.fills += 1
            self.closing_fills += 1

        return matched

    # ---- rung 1: per-session, own-contract, flat at the close -------------
    def _flatten(self, price: Decimal, fee: bool) -> int:
        """Realise the whole position at ``price`` (fee per contract if ``fee``)."""
        n = abs(self.inventory)
        if n == 0:
            return 0
        sign = 1 if self.inventory > 0 else -1
        self.ac_loss -= sign * n * (price - self.inventory_price) * Decimal("100")
        if fee:
            self.ac_loss += FEE_PER_CONTRACT * n
            self.fees_charged += FEE_PER_CONTRACT * n
        self.inventory = 0
        return n

    def run_sessions(self, sessions: Iterable[Session], step: Decimal):
        """Rung >= 1 loop. Each session: quote on prints in [09:00, 14:25),
        close the residual at the first print in [14:25, 14:29:59] (a
        position-reducing trade: fee per contract, as the naive engine charges
        on reductions), mark anything still open at the close (no fee)."""
        if not self.options.aligned:
            raise ValueError("run_sessions is the aligned (rung >= 1) loop")
        for day, ticker, ticks, close in sessions:
            self.ticker = ticker
            closed = False
            last_price = None
            for ts, price in ticks:
                t = ts.time()
                if t < QUOTE_FROM or t > CLOSE_TO:
                    continue
                self.cur_date = ts
                last_price = price
                if t < QUOTE_TO:
                    self.handle_force_sell(price)
                    self.update_bid_ask(price, step, ts)
                elif not closed:
                    self.bid_price = self.ask_price = None
                    n = self._flatten(price, fee=True)
                    self.fills += n
                    self.closing_fills += n
                    self.closeout_contracts += n
                    closed = True
            if self.inventory != 0:
                mark = close if close is not None else last_price
                self.marked_contracts += self._flatten(mark, fee=False)
            self.update_pnl(close if close is not None else (last_price or Decimal("0")))
            self.ac_loss = Decimal("0.0")
            self.bid_price = None
            self.ask_price = None
            self.old_timestamp = None
            self.tracking_dates.append(day)
            self.daily_inventory.append(self.inventory)
        self.metric = Metric(self.daily_returns, None)
