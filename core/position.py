"""
Position data model for portfolio tracking
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Tuple


@dataclass
class Position:
    """
    Position tracking for a single contract

    Tracks:
    - Current quantity (positive = long, negative = short)
    - Individual entry prices (FIFO queue)
    - Average entry price (calculated from entry_prices)
    - Realized and unrealized PnL
    - Total fees paid

    Example:
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))
        pos.add_contracts(Decimal("1540.9"), 1)
        pos.update_unrealized_pnl(Decimal("1543.0"))
    """
    contract: str
    quantity: int  # Positive = long, Negative = short
    average_price: Decimal  # TODO: Will become @property after Portfolio update
    entry_prices: List[Decimal] = field(default_factory=list)  # FIFO queue of individual entry prices
    realized_pnl: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    total_fees: Decimal = Decimal('0')

    # Contract multiplier (each contract = 100 units)
    CONTRACT_MULTIPLIER: int = 100

    def add_contracts(self, price: Decimal, qty: int):
        """
        Add contracts to position (FIFO queue)

        Args:
            price: Entry price for the contracts
            qty: Number of contracts to add
        """
        for _ in range(qty):
            self.entry_prices.append(price)
        # Note: quantity sign is managed by Portfolio (positive for LONG, negative for SHORT)

    def remove_contracts(self, qty: int) -> List[Decimal]:
        """
        Remove contracts from position (FIFO - First In First Out)

        Args:
            qty: Number of contracts to remove

        Returns:
            List of entry prices for removed contracts (in FIFO order)
        """
        removed = []
        for _ in range(min(qty, len(self.entry_prices))):
            if self.entry_prices:
                removed.append(self.entry_prices.pop(0))  # FIFO: remove from front
        return removed

    def get_individual_pnls(self, current_price: Decimal) -> List[Tuple[Decimal, Decimal]]:
        """
        Get PnL for each individual contract

        Args:
            current_price: Current market price

        Returns:
            List of (entry_price, pnl_in_points) for each contract

        Example:
            [(1540.9, -3.0), (1543.0, -0.9)] for 2 SHORT contracts at market 1543.9
        """
        result = []
        for entry in self.entry_prices:
            if self.quantity > 0:  # LONG
                pnl_pts = current_price - entry
            else:  # SHORT (quantity < 0)
                pnl_pts = entry - current_price
            result.append((entry, pnl_pts))
        return result

    def update_unrealized_pnl(self, current_price: Decimal):
        """
        Calculate unrealized PnL based on current market price

        Uses individual entry prices if available, otherwise falls back to average_price.

        Formula:
            For long: sum((current_price - entry) * multiplier) for each contract
            For short: sum((entry - current_price) * multiplier) for each contract

        Args:
            current_price: Current market price
        """
        if not self.entry_prices:
            # Fallback to average_price for backward compatibility
            if self.quantity > 0:
                self.unrealized_pnl = (
                    (current_price - self.average_price)
                    * abs(self.quantity)
                    * self.CONTRACT_MULTIPLIER
                )
            elif self.quantity < 0:
                self.unrealized_pnl = (
                    (self.average_price - current_price)
                    * abs(self.quantity)
                    * self.CONTRACT_MULTIPLIER
                )
            else:
                self.unrealized_pnl = Decimal('0')
        else:
            # Use individual entry prices for precise calculation
            total = Decimal('0')
            for entry in self.entry_prices:
                if self.quantity > 0:  # LONG
                    total += (current_price - entry) * self.CONTRACT_MULTIPLIER
                else:  # SHORT
                    total += (entry - current_price) * self.CONTRACT_MULTIPLIER
            self.unrealized_pnl = total

    def total_pnl(self) -> Decimal:
        """
        Total PnL = realized + unrealized - fees

        Returns:
            Total profit/loss
        """
        return self.realized_pnl + self.unrealized_pnl - self.total_fees

    def is_flat(self) -> bool:
        """Check if position is flat (no holdings)"""
        return self.quantity == 0

    def is_long(self) -> bool:
        """Check if position is long"""
        return self.quantity > 0

    def is_short(self) -> bool:
        """Check if position is short"""
        return self.quantity < 0

    def get_market_value(self, current_price: Decimal) -> Decimal:
        """
        Get current market value of position

        Args:
            current_price: Current market price

        Returns:
            Market value (quantity * price * multiplier)
        """
        return (
            abs(self.quantity)
            * current_price
            * self.CONTRACT_MULTIPLIER
        )

    def __str__(self):
        return (
            f"Position({self.contract} qty={self.quantity} "
            f"avg_px={self.average_price} "
            f"pnl={self.total_pnl():.2f})"
        )

    def __repr__(self):
        return self.__str__()
