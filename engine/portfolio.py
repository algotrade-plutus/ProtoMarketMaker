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

        # Cumulative realized P&L tracking (like ac_loss in original)
        # Negative value = cumulative gains (matches original's ac_loss convention)
        self.cumulative_realized_pnl = Decimal('0')

        # PLUTUS evaluator
        self.evaluator: Optional[PerformanceEvaluator] = None

        self.logger = logging.getLogger(__name__)

        # Subscribe to events
        self.event_bus.subscribe(EventType.FILL, self.on_fill_event)
        self.event_bus.subscribe(EventType.MARKET_DATA, self.on_market_data)
        self.event_bus.subscribe(EventType.TIME, self.on_time_event)
        self.event_bus.subscribe(EventType.ROLLOVER, self.on_rollover_event)

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

        IMPORTANT: Uses last settlement NAV, not current intraday NAV.
        This matches original backtest behavior and prevents over-leveraging
        based on unrealized intraday gains.

        Args:
            contract: Contract symbol
            price: Current price

        Returns:
            Number of contracts that can be placed
        """
        # Use last settlement NAV (like original's daily_assets[-1])
        # NOT current intraday NAV (which includes unrealized PnL)
        if len(self.daily_nav) > 0:
            nav = self.daily_nav[-1]
        else:
            nav = self.initial_capital

        margin_per_contract = price * Decimal('100') * Decimal('0.17')

        if margin_per_contract == 0:
            self.logger.warning(f"Margin per contract is 0! price={price}")
            return 0

        total_placeable = int(nav / margin_per_contract)

        # Calculate TOTAL position across ALL contracts (not just this one)
        total_position = sum(abs(p.quantity) for p in self.positions.values())

        available = max(total_placeable - total_position, 0)

        return available

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

        # Determine if this is opening or closing a position
        is_closing = (position.quantity > 0 and not is_buy) or \
                     (position.quantity < 0 and is_buy)

        # Calculate realized PnL if closing/reducing position
        if is_closing:
            # Closing position - realize P&L
            # Fee model: 40 total per round trip (20 open + 20 close)
            # We charge all 40 at close time to match original backtest
            if position.quantity > 0:  # Closing long
                realized_pnl = (
                    (event.fill_price - position.average_price)
                    * Decimal('100')
                    - event.fee
                )
            else:  # Closing short
                realized_pnl = (
                    (position.average_price - event.fill_price)
                    * Decimal('100')
                    - event.fee
                )
            position.realized_pnl += realized_pnl

            # Track cumulative realized P&L (like ac_loss in original)
            # Use -= to make negative values represent gains (matches original convention)
            self.cumulative_realized_pnl -= realized_pnl

            # Note: We do NOT update cash here. Cash only updates at settlement.
            # This matches original's behavior where daily_assets only updates at settlement.
        else:
            # Opening position - NO fee charged yet (deferred until close)
            # This matches original backtest behavior
            # Futures contracts don't require paying the full contract value upfront
            pass

        # Update position quantity and average price
        if not is_closing:
            # Opening or adding to position
            old_quantity = abs(position.quantity)
            new_quantity = old_quantity + 1

            if new_quantity > 0:
                position.average_price = (
                    position.average_price * old_quantity + event.fill_price
                ) / new_quantity

        position.quantity += quantity_change
        position.total_fees += event.fee

        self.logger.info(
            f"Portfolio updated: {event.contract} position={position.quantity} "
            f"avg_price={position.average_price:.2f} cash={self.cash:.2f} "
            f"NAV={self.calculate_nav():.2f}"
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
            # Update positions with close prices for settlement (if provided)
            # This ensures NAV is calculated using official close prices, not last tick
            if hasattr(event, 'close_prices') and event.close_prices:
                for contract, close_price in event.close_prices.items():
                    if contract in self.positions:
                        position = self.positions[contract]

                        # Calculate and "lock in" unrealized PnL before reset
                        # This matches original backtest's daily asset update
                        if position.quantity != 0:
                            # Calculate settlement PnL (close price vs current average)
                            sign = 1 if position.quantity > 0 else -1
                            settlement_pnl = (
                                sign * abs(position.quantity) *
                                (close_price - position.average_price) * Decimal('100')
                            )
                            # Add to cash (locks in the PnL)
                            self.cash += settlement_pnl

                            # Reset average_price to close_price for next day
                            # This prevents double-counting when position is closed
                            position.average_price = close_price

                            # Reset unrealized PnL to zero since we just locked it in
                            position.unrealized_pnl = Decimal('0')

                    # Also update current prices cache
                    self.current_prices[contract] = close_price

            # Add cumulative realized P&L to cash (matches original's ac_loss handling)
            # Original formula: new_asset = cur_asset + (unrealized_pnl - ac_loss)
            # Since ac_loss is negative for gains, this becomes: cur_asset + unrealized + |ac_loss|
            # cumulative_realized_pnl is negative for gains, so we negate it to add gains
            self.cash += (-self.cumulative_realized_pnl)

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

    def on_rollover_event(self, event):
        """
        Handle contract rollover (e.g., VN30F2201 -> VN30F2202)

        Matches original backtest's move_f1_to_f2() logic:
        1. Close position in old contract (realize P&L)
        2. Reopen same position in new contract
        3. Charge rollover fees

        Args:
            event: RolloverEvent with old/new contract and prices
        """
        from core.event import RolloverEvent
        if not isinstance(event, RolloverEvent):
            return

        old_contract = event.old_contract
        new_contract = event.new_contract
        old_price = event.old_price
        new_price = event.new_price

        # Get position in old contract
        if old_contract in self.positions:
            old_position = self.positions[old_contract]

            if old_position.quantity != 0:
                # Calculate P&L from closing old contract position
                # This matches original's logic in move_f1_to_f2()
                # NOTE: Original calculates per-contract P&L, not total
                if old_position.quantity > 0:
                    # Long position: P&L = (close_price - entry_price) * 100 per contract
                    rollover_pnl = (old_price - old_position.average_price) * Decimal('100')
                else:
                    # Short position: P&L = (entry_price - close_price) * 100 per contract
                    rollover_pnl = (old_position.average_price - old_price) * Decimal('100')

                # Charge rollover fees (FEE_PER_CONTRACT * quantity)
                # Original charges 40 per contract (20 close + 20 reopen)
                rollover_fees = Decimal('40') * abs(old_position.quantity)
                net_rollover_pnl = rollover_pnl - rollover_fees

                # Update cumulative realized P&L (like ac_loss in original)
                # Note: We use -= because cumulative_realized_pnl is negative for gains
                self.cumulative_realized_pnl -= net_rollover_pnl

                # Create position in new contract with same quantity
                new_position = self.get_position(new_contract)
                new_position.quantity = old_position.quantity
                new_position.average_price = new_price

                # Close old position
                old_position.quantity = 0
                old_position.average_price = Decimal('0')
                old_position.unrealized_pnl = Decimal('0')

                self.logger.info(
                    f"Contract rollover: {old_contract} -> {new_contract} | "
                    f"quantity={new_position.quantity} | "
                    f"old_price={old_price} | new_price={new_price} | "
                    f"rollover_pnl={rollover_pnl:.2f} | fees={rollover_fees:.2f} | "
                    f"net_pnl={net_rollover_pnl:.2f}"
                )

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

        try:
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
        except Exception as e:
            self.logger.warning(f"PLUTUS evaluation error: {e}")
            # Return basic metrics calculated from daily returns
            if len(self.daily_returns) > 0:
                import numpy as np
                returns_array = [float(r) for r in self.daily_returns]
                mean_return = np.mean(returns_array)
                std_return = np.std(returns_array)
                sharpe = mean_return / std_return * np.sqrt(252) if std_return > 0 else 0

                return {
                    'sharpe_ratio': sharpe,
                    'sortino_ratio': 0.0,
                    'calmar_ratio': 0.0,
                    'maximum_drawdown': 0.0,
                    'annual_return': mean_return * 252,
                    'volatility': std_return * np.sqrt(252),
                    'value_at_risk_95': 0.0,
                    'conditional_var_95': 0.0,
                }
            else:
                return {
                    'sharpe_ratio': 0.0,
                    'sortino_ratio': 0.0,
                    'calmar_ratio': 0.0,
                    'maximum_drawdown': 0.0,
                    'annual_return': 0.0,
                    'volatility': 0.0,
                    'value_at_risk_95': 0.0,
                    'conditional_var_95': 0.0,
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
