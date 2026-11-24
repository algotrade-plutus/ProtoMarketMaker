"""Naive-engine variants for the RIVF'26 MarketMaker attribution ladder.

Owner framing: the naive engine's behaviour *is* the algorithm A under study;
the naive engine and Plutus are environments. These options therefore change
only the naive *environment's* execution rules, never A (no flattening, no
14:25 cutoff, no single-contract feed: A's rows, quoting and roll are the
base engine's). ``backtest.Backtesting`` is untouched; every rung is an opt-in
option on this subclass, so the default naive output stays byte-identical.
Pure: no plutus import (the dated IM rule is implemented locally, below).

Rungs (cumulative in ``experiments/mm_ladder.py``, independent flags here):

N1. ``own_price_fills`` -- a crossed quote books at its own price (the bid or
    the ask), not at the print that crossed it.
N2. ``dated_im`` -- contract capacity at the dated VSD initial-margin rate
    (13% before 2022-12-15, 17% from it) instead of the flat 17%.
N3. ``fee_every_fill`` -- ``FEE_PER_CONTRACT`` on every fill, not only on
    position-reducing ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from proto_market_maker.backtest import Backtesting, FEE_PER_CONTRACT
from proto_market_maker.utils import from_cash_to_tradeable_contracts

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
    own_price_fills: bool = False
    dated_im: bool = False
    fee_every_fill: bool = False

    @classmethod
    def rung(cls, n: int) -> "NaiveOptions":
        """Cumulative ladder rung N0..N3 (0 = the naive engine as-is)."""
        if not 0 <= n <= 3:
            raise ValueError(n)
        return cls(own_price_fills=n >= 1, dated_im=n >= 2, fee_every_fill=n >= 3)


class NaiveVariant(Backtesting):
    """``Backtesting`` with the ladder options. ``run`` is inherited (A's loop
    unchanged); with all options off the fill rule below reduces to the base
    rule, plus fill counters."""

    def __init__(self, capital: Decimal, options: NaiveOptions = NaiveOptions(),
                 printable: bool = False):
        super().__init__(capital, printable=printable)
        self.options = options
        self.cur_date = None
        self.fills = 0              # contracts filled
        self.closing_fills = 0      # position-reducing contracts (= round trips)
        self.forced_reductions = 0
        self.fees_charged = Decimal("0")   # thousand dong, for reporting

    # ---- N2: dated IM ------------------------------------------------
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

    # ---- N1 and N3: fill price and fee -------------------------------
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
