"""
Risk Manager

Responsibilities:
- Pre-trade risk checks
- Position limit enforcement
- Margin requirement validation
"""
from decimal import Decimal
import logging

from protomarketmaker.core import Order


class RiskManager:
    """
    Risk Manager for pre-trade checks

    Validates orders before submission to prevent:
    - Insufficient margin
    - Invalid prices
    - Excessive position sizes

    Example:
        risk = RiskManager(portfolio)
        if risk.validate_order(order):
            oms.submit_order(order)
    """

    def __init__(self, portfolio):
        """
        Initialize risk manager

        Args:
            portfolio: PortfolioManager instance
        """
        self.portfolio = portfolio
        self.logger = logging.getLogger(__name__)

    def validate_order(self, order: Order) -> bool:
        """
        Pre-trade risk checks

        Args:
            order: Order to validate

        Returns:
            True if order passes all checks, False otherwise
        """
        from protomarketmaker.core.enums import OrderSide

        # Check 1: Price reasonability
        if order.price <= 0:
            self.logger.warning(
                f"Order rejected: invalid price {order.price}"
            )
            return False

        # Check 2: Quantity validation
        if order.quantity <= 0:
            self.logger.warning(
                f"Order rejected: invalid quantity {order.quantity}"
            )
            return False

        # Check 3: Margin availability (only for orders that increase position)
        position = self.portfolio.get_position(order.contract)
        is_buy = order.side == OrderSide.BID
        is_sell = order.side == OrderSide.ASK

        # Determine if this order increases position (requires margin)
        # or decreases position (no margin required)
        requires_margin = False

        if is_buy and position.quantity >= 0:
            # Buying when flat or long = increasing long position
            requires_margin = True
        elif is_sell and position.quantity <= 0:
            # Selling when flat or short = increasing short position
            requires_margin = True
        # else: closing an existing position, no margin required

        if requires_margin:
            available_margin = self.portfolio.get_available_margin(
                order.contract, order.price
            )

            if order.quantity > available_margin:
                self.logger.warning(
                    f"Order rejected: insufficient margin "
                    f"(need {order.quantity}, have {available_margin})"
                )
                return False

        return True

    def check_margin_requirement(self) -> bool:
        """
        Check if portfolio meets margin requirements

        Returns:
            True if margin is sufficient, False otherwise
        """
        nav = self.portfolio.calculate_nav()

        # Calculate required margin for all positions
        required_margin = Decimal('0')
        for position in self.portfolio.positions.values():
            if position.quantity != 0:
                price = self.portfolio.current_prices.get(
                    position.contract,
                    position.average_price
                )
                required_margin += (
                    abs(position.quantity)
                    * price
                    * Decimal('100')
                    * Decimal('0.17')
                )

        if nav < required_margin:
            self.logger.warning(
                f"Margin call: NAV={nav:.2f}, Required={required_margin:.2f}"
            )
            return False

        return True
