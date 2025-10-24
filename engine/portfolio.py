"""
Portfolio Manager

Responsibilities:
- Track positions across all contracts
- Manage cash and margin
- Calculate real-time PnL
- Generate performance metrics
"""
from typing import Dict, List, Optional
from datetime import datetime, date
from decimal import Decimal
import logging

from core.position import Position
from core.event import EventBus, FillEvent, MarketDataEvent, TimeEvent
from core.enums import EventType

# PLUTUS will be imported when available
try:
    from plutus.evaluation import PerformanceEvaluator
    PLUTUS_AVAILABLE = True
except ImportError:
    PLUTUS_AVAILABLE = False
    PerformanceEvaluator = None


class PortfolioManager:
    """
    Portfolio Manager

    Tracks all positions, cash, and PnL in real-time.
    Updates on fill events and market data events.

    Example:
        portfolio = PortfolioManager(event_bus, Decimal("500000"))
        nav = portfolio.calculate_nav()
    """

    def __init__(self, event_bus: EventBus, initial_capital: Decimal):
        """
        Initialize portfolio

        Args:
            event_bus: Event bus for subscribing to events
            initial_capital: Starting cash
        """
        self.event_bus = event_bus
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}

        # Performance tracking
        self.daily_returns: List[Decimal] = []
        self.daily_nav: List[Decimal] = [initial_capital]
        self.tracking_dates: List[date] = []

        # Market prices cache
        self.current_prices: Dict[str, Decimal] = {}

        # PLUTUS evaluator
        self.evaluator: Optional[PerformanceEvaluator] = None

        self.logger = logging.getLogger(__name__)

        # Subscribe to events
        self.event_bus.subscribe(EventType.FILL, self.on_fill_event)
        self.event_bus.subscribe(EventType.MARKET_DATA, self.on_market_data)
        self.event_bus.subscribe(EventType.TIME, self.on_time_event)

    def get_position(self, contract: str) -> Position:
        """
        Get or create position for contract

        Args:
            contract: Contract symbol

        Returns:
            Position object
        """
        if contract not in self.positions:
            self.positions[contract] = Position(
                contract=contract,
                quantity=0,
                average_price=Decimal('0')
            )
        return self.positions[contract]

    def calculate_nav(self) -> Decimal:
        """
        Calculate Net Asset Value = cash + unrealized PnL

        Returns:
            Total portfolio value
        """
        total_unrealized_pnl = sum(
            pos.unrealized_pnl for pos in self.positions.values()
        )
        return self.cash + total_unrealized_pnl

    def get_available_margin(self, contract: str, price: Decimal) -> int:
        """
        Calculate maximum placeable contracts (17% margin)

        Args:
            contract: Contract symbol
            price: Current price

        Returns:
            Number of contracts that can be placed
        """
        nav = self.calculate_nav()
        margin_per_contract = price * Decimal('100') * Decimal('0.17')

        if margin_per_contract == 0:
            return 0

        total_placeable = int(nav / margin_per_contract)
        current_position = abs(self.get_position(contract).quantity)
        return max(total_placeable - current_position, 0)

    def on_fill_event(self, event: FillEvent):
        """
        Update portfolio on order fill

        Args:
            event: Fill event with execution details
        """
        position = self.get_position(event.contract)

        # Determine buy or sell
        is_buy = event.side == "BID"
        quantity_change = 1 if is_buy else -1

        # Calculate realized PnL if closing/reducing position
        if (position.quantity > 0 and not is_buy) or \
           (position.quantity < 0 and is_buy):
            # Closing position
            if position.quantity > 0:  # Closing long
                realized_pnl = (
                    (event.fill_price - position.average_price)
                    * Decimal('100')
                )
            else:  # Closing short
                realized_pnl = (
                    (position.average_price - event.fill_price)
                    * Decimal('100')
                )
            position.realized_pnl += realized_pnl

        # Update position quantity and average price
        if (position.quantity >= 0 and is_buy) or \
           (position.quantity <= 0 and not is_buy):
            # Opening or adding to position
            old_quantity = abs(position.quantity)
            new_quantity = old_quantity + 1

            if new_quantity > 0:
                position.average_price = (
                    position.average_price * old_quantity + event.fill_price
                ) / new_quantity

        position.quantity += quantity_change
        position.total_fees += event.fee

        # Update cash
        cash_flow = event.fill_price * Decimal('100') + event.fee
        self.cash -= cash_flow if is_buy else -cash_flow

        self.logger.info(
            f"Portfolio updated: {event.contract} position={position.quantity} "
            f"avg_price={position.average_price:.2f} cash={self.cash:.2f}"
        )

    def on_market_data(self, event: MarketDataEvent):
        """
        Update unrealized PnL on market data

        Args:
            event: Market data event
        """
        self.current_prices[event.contract] = event.price

        if event.contract in self.positions:
            position = self.positions[event.contract]
            position.update_unrealized_pnl(event.price)

    def on_time_event(self, event: TimeEvent):
        """
        Handle daily settlement and performance calculation

        Args:
            event: Time event (e.g., DAILY_SETTLEMENT)
        """
        if event.event_name == "DAILY_SETTLEMENT":
            nav = self.calculate_nav()

            if len(self.daily_nav) > 0:
                daily_return = nav / self.daily_nav[-1] - 1
                self.daily_returns.append(daily_return)

            self.daily_nav.append(nav)
            if event.date:
                self.tracking_dates.append(event.date.date())

            # Update performance evaluator with PLUTUS (if available)
            if PLUTUS_AVAILABLE and len(self.daily_returns) > 0:
                self.evaluator = PerformanceEvaluator.from_returns(
                    returns=self.daily_returns,
                    annualization_factor=252,
                    risk_free_rate=Decimal('0.06'),  # 6% annual
                    min_acceptable_return=Decimal('0.07')
                )

                self.logger.info(
                    f"Daily settlement: NAV={nav:.2f} "
                    f"Return={daily_return*100 if len(self.daily_returns) > 0 else 0:.4f}% "
                    f"Sharpe={self.evaluator.sharpe_ratio:.4f}"
                )
            else:
                self.logger.info(
                    f"Daily settlement: NAV={nav:.2f} "
                    f"Return={daily_return*100 if len(self.daily_returns) > 0 else 0:.4f}%"
                )

            # Reset daily accumulated fees
            for position in self.positions.values():
                position.total_fees = Decimal('0')

    def get_performance_metrics(self) -> dict:
        """
        Get all performance metrics from PLUTUS evaluator

        Returns:
            Dictionary of performance metrics
        """
        if not PLUTUS_AVAILABLE:
            return {'error': 'PLUTUS not available'}

        if not self.evaluator:
            return {'error': 'No performance data yet'}

        return {
            'sharpe_ratio': float(self.evaluator.sharpe_ratio),
            'sortino_ratio': float(self.evaluator.sortino_ratio),
            'calmar_ratio': float(self.evaluator.calmar_ratio),
            'maximum_drawdown': float(self.evaluator.maximum_drawdown),
            'annual_return': float(self.evaluator.annual_return),
            'volatility': float(self.evaluator.volatility),
            'value_at_risk_95': float(self.evaluator.value_at_risk_95),
            'conditional_var_95': float(self.evaluator.conditional_var_95),
        }

    def get_summary(self) -> dict:
        """Get portfolio summary"""
        return {
            'cash': float(self.cash),
            'nav': float(self.calculate_nav()),
            'positions': {
                contract: {
                    'quantity': pos.quantity,
                    'average_price': float(pos.average_price),
                    'unrealized_pnl': float(pos.unrealized_pnl),
                    'realized_pnl': float(pos.realized_pnl),
                    'total_fees': float(pos.total_fees),
                    'total_pnl': float(pos.total_pnl())
                }
                for contract, pos in self.positions.items()
                if not pos.is_flat()
            },
            'total_return': float(
                (self.calculate_nav() / self.initial_capital - 1) * 100
            ) if self.initial_capital > 0 else 0
        }
