"""The pure quoting seam: inventory-skewed two-sided quotes.

Extracted verbatim from ``backtest.update_bid_ask`` so the naive engine and the
faithful Plutus driver quote from the identical function. The requote *cadence*
(every 15 s, or on a fill) is NOT here; it is each arm's own loop. This function
is pure and imports nothing from plutus::

    bid = price - step * (max(inventory, 0) * 0.02 + 1)
    ask = price - step * (min(inventory, 0) * 0.02 - 1)

Both are quantized to the 0.1-point grid with ROUND_HALF_UP, exactly as the
inline engine did (the float intermediate is kept for exact reproduction).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def quote(price: Decimal, inventory: int, step: Decimal) -> tuple[Decimal, Decimal]:
    bid = (price - step * Decimal(max(inventory, 0) * 0.02 + 1)).quantize(
        Decimal("0.0"), rounding=ROUND_HALF_UP)
    ask = (price - step * Decimal(min(inventory, 0) * 0.02 - 1)).quantize(
        Decimal("0.0"), rounding=ROUND_HALF_UP)
    return bid, ask
