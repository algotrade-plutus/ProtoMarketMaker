"""
Position data model for portfolio tracking
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Position:
    """
    Position tracking for a single contract

    Tracks:
    - Current quantity (positive = long, negative = short)
    - Average entry price
    - Realized and unrealized PnL
    - Total fees paid

    Example:
        pos = Position(contract="VN30F1M", quantity=0, average_price=Decimal("0"))
        pos.update_unrealized_pnl(Decimal("1250.5"))
    """
    contract: str
    quantity: int  # Positive = long, Negative = short
    average_price: Decimal
    realized_pnl: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    total_fees: Decimal = Decimal('0')

    # Contract multiplier (each contract = 100 units)
    CONTRACT_MULTIPLIER: int = 100

    def update_unrealized_pnl(self, current_price: Decimal):
        """
        Calculate unrealized PnL based on current market price

        Formula:
            For long: (current_price - avg_price) * quantity * multiplier
            For short: (avg_price - current_price) * |quantity| * multiplier

        Args:
            current_price: Current market price
        """
        if self.quantity > 0:
            # Long position
            self.unrealized_pnl = (
                (current_price - self.average_price)
                * abs(self.quantity)
                * self.CONTRACT_MULTIPLIER
            )
        elif self.quantity < 0:
            # Short position
            self.unrealized_pnl = (
                (self.average_price - current_price)
                * abs(self.quantity)
                * self.CONTRACT_MULTIPLIER
            )
        else:
            # Flat position
            self.unrealized_pnl = Decimal('0')

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
