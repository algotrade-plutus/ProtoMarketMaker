"""
Order data model for paper trading system
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
import uuid

from core.enums import OrderSide, OrderStatus


@dataclass
class Order:
    """
    Order object with full lifecycle tracking

    Represents a single order in the trading system.
    Tracks state changes from creation to completion.

    Example:
        order = Order(
            contract="VN30F1M",
            side=OrderSide.BID,
            price=Decimal("1250.5"),
            quantity=1
        )
    """
    # Required fields
    contract: str = ""
    side: OrderSide = OrderSide.BID
    price: Decimal = Decimal('0')
    quantity: int = 1

    # Auto-generated fields
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: OrderStatus = OrderStatus.CREATED
    created_at: datetime = field(default_factory=datetime.now)

    # Lifecycle timestamps
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    # Fill information
    filled_price: Optional[Decimal] = None
    filled_quantity: int = 0

    def is_active(self) -> bool:
        """Check if order is in active state"""
        return self.status.is_active()

    def is_terminal(self) -> bool:
        """Check if order is in terminal state"""
        return self.status.is_terminal()

    def is_filled(self) -> bool:
        """Check if order is fully filled"""
        return self.status == OrderStatus.FILLED

    def is_cancelled(self) -> bool:
        """Check if order was cancelled"""
        return self.status == OrderStatus.CANCELLED

    def is_rejected(self) -> bool:
        """Check if order was rejected"""
        return self.status == OrderStatus.REJECTED

    def can_cancel(self) -> bool:
        """Check if order can be cancelled"""
        return self.is_active()

    def get_unfilled_quantity(self) -> int:
        """Get remaining unfilled quantity"""
        return self.quantity - self.filled_quantity

    def __str__(self):
        return (
            f"Order({self.order_id[:8]}... {self.side.value} "
            f"{self.contract} @ {self.price} x{self.quantity} "
            f"[{self.status.value}])"
        )

    def __repr__(self):
        return self.__str__()
