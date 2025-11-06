"""
Backtest Results

Data structures for storing and exporting backtest results.
"""
from dataclasses import dataclass, asdict
from decimal import Decimal
from datetime import date
from typing import Optional
import json


@dataclass
class BacktestResults:
    """
    Complete backtest results

    Contains all performance metrics, trading statistics,
    and portfolio timeline data.
    """

    # Performance metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    hpr: float  # Holding Period Return
    annual_return: float
    monthly_return: float

    # Trading statistics
    total_trades: int
    buy_trades: int
    sell_trades: int
    total_fees: Decimal

    # Portfolio timeline
    initial_capital: Decimal
    final_capital: Decimal
    daily_assets: list[Decimal]
    daily_returns: list[Decimal]
    daily_inventory: list[int]
    tracking_dates: list[date]

    # Contract rolling
    expirations_handled: int

    # Runtime statistics
    events_processed: int
    duration_seconds: float

    def to_dict(self) -> dict:
        """
        Convert to dictionary with JSON-serializable types

        Returns:
            Dictionary representation
        """
        result = asdict(self)

        # Convert Decimal to float
        result['total_fees'] = float(self.total_fees)
        result['initial_capital'] = float(self.initial_capital)
        result['final_capital'] = float(self.final_capital)
        result['daily_assets'] = [float(x) for x in self.daily_assets]
        result['daily_returns'] = [float(x) for x in self.daily_returns]

        # Convert dates to strings
        result['tracking_dates'] = [d.isoformat() for d in self.tracking_dates]

        return result

    def to_json(self, filepath: Optional[str] = None, indent: int = 2) -> str:
        """
        Export to JSON format

        Args:
            filepath: Optional file path to save JSON
            indent: JSON indentation (default: 2)

        Returns:
            JSON string
        """
        json_str = json.dumps(self.to_dict(), indent=indent)

        if filepath:
            with open(filepath, 'w') as f:
                f.write(json_str)

        return json_str

    @classmethod
    def from_dict(cls, data: dict) -> 'BacktestResults':
        """
        Create from dictionary

        Args:
            data: Dictionary representation

        Returns:
            BacktestResults instance
        """
        # Convert back to proper types
        data['total_fees'] = Decimal(str(data['total_fees']))
        data['initial_capital'] = Decimal(str(data['initial_capital']))
        data['final_capital'] = Decimal(str(data['final_capital']))
        data['daily_assets'] = [Decimal(str(x)) for x in data['daily_assets']]
        data['daily_returns'] = [Decimal(str(x)) for x in data['daily_returns']]
        data['tracking_dates'] = [
            date.fromisoformat(d) for d in data['tracking_dates']
        ]

        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> 'BacktestResults':
        """
        Load from JSON string

        Args:
            json_str: JSON string

        Returns:
            BacktestResults instance
        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    def summary(self) -> str:
        """
        Generate text summary

        Returns:
            Formatted summary string
        """
        return f"""
Backtest Results Summary
========================

Performance Metrics:
  Sharpe Ratio:        {self.sharpe_ratio:.4f}
  Sortino Ratio:       {self.sortino_ratio:.4f}
  Maximum Drawdown:    {self.max_drawdown:.2%}
  HPR:                 {self.hpr:.2%}
  Annual Return:       {self.annual_return:.2%}
  Monthly Return:      {self.monthly_return:.2%}

Trading Statistics:
  Total Trades:        {self.total_trades}
  Buy Trades:          {self.buy_trades}
  Sell Trades:         {self.sell_trades}
  Total Fees:          {self.total_fees:,.2f}

Portfolio:
  Initial Capital:     {self.initial_capital:,.2f}
  Final Capital:       {self.final_capital:,.2f}
  Total Return:        {(self.final_capital / self.initial_capital - 1):.2%}

Contract Rolling:
  Expirations Handled: {self.expirations_handled}

Runtime:
  Events Processed:    {self.events_processed:,}
  Duration:            {self.duration_seconds:.2f}s
  Events/sec:          {self.events_processed / self.duration_seconds:.0f}
"""

    def __str__(self) -> str:
        """String representation"""
        return self.summary()
