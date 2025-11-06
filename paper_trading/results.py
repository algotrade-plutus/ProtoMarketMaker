"""
Paper Trading Results

This module provides a dataclass for storing and exporting paper trading session results.
Mirrors BacktestResults structure for consistency.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, date
from decimal import Decimal
from typing import List
import json


@dataclass
class PaperTradingResults:
    """
    Comprehensive results from paper trading session

    Mirrors BacktestResults structure for consistency with event-driven backtesting.
    """

    # ===== Session Metadata =====
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    mode: str  # "redis" or "csv"

    # ===== Performance Metrics (from PLUTUS) =====
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    hpr: float  # Holding period return

    # ===== Trading Statistics (from Monitor) =====
    total_trades: int
    buy_trades: int
    sell_trades: int
    total_fees: Decimal

    # ===== Portfolio Timeline (from Portfolio) =====
    initial_capital: Decimal
    final_nav: Decimal
    daily_nav: List[Decimal]
    daily_returns: List[Decimal]
    tracking_dates: List[date]

    # ===== Redis-Specific Metrics =====
    messages_received: int
    messages_processed: int
    avg_latency_ms: float
    reconnect_count: int

    # ===== Contract Rollover Tracking =====
    rollovers: List[dict]  # [{old_contract, new_contract, timestamp, pnl}]

    def to_dict(self) -> dict:
        """
        Convert to dictionary (JSON-serializable)

        Returns:
            Dictionary representation grouped by category with all Decimal/datetime converted to primitives
        """
        return {
            'session': {
                'start_time': self.start_time.isoformat(),
                'end_time': self.end_time.isoformat(),
                'duration_seconds': self.duration_seconds,
                'mode': self.mode
            },
            'performance': {
                'initial_capital': str(self.initial_capital),
                'final_nav': str(self.final_nav),
                'hpr': float(self.hpr),
                'sharpe_ratio': float(self.sharpe_ratio),
                'sortino_ratio': float(self.sortino_ratio),
                'max_drawdown': float(self.max_drawdown),
                'daily_nav': [float(x) for x in self.daily_nav],
                'daily_returns': [float(x) for x in self.daily_returns],
                'tracking_dates': [d.isoformat() for d in self.tracking_dates]
            },
            'trading': {
                'total_trades': self.total_trades,
                'buy_trades': self.buy_trades,
                'sell_trades': self.sell_trades,
                'total_fees': str(self.total_fees)
            },
            'redis_metrics': {
                'messages_received': self.messages_received,
                'messages_processed': self.messages_processed,
                'avg_latency_ms': float(self.avg_latency_ms),
                'reconnect_count': self.reconnect_count
            },
            'rollovers': self.rollovers
        }

    def to_json(self, path: str):
        """
        Export to JSON file

        Args:
            path: File path to save JSON
        """
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> 'PaperTradingResults':
        """
        Load from JSON file

        Args:
            path: File path to load JSON from

        Returns:
            PaperTradingResults instance
        """
        with open(path, 'r') as f:
            structured_data = json.load(f)

        # Flatten structured format back to dataclass format
        return cls(
            # Session
            start_time=datetime.fromisoformat(structured_data['session']['start_time']),
            end_time=datetime.fromisoformat(structured_data['session']['end_time']),
            duration_seconds=structured_data['session']['duration_seconds'],
            mode=structured_data['session']['mode'],
            # Performance
            initial_capital=Decimal(structured_data['performance']['initial_capital']),
            final_nav=Decimal(structured_data['performance']['final_nav']),
            hpr=structured_data['performance']['hpr'],
            sharpe_ratio=structured_data['performance']['sharpe_ratio'],
            sortino_ratio=structured_data['performance']['sortino_ratio'],
            max_drawdown=structured_data['performance']['max_drawdown'],
            daily_nav=[Decimal(str(x)) for x in structured_data['performance']['daily_nav']],
            daily_returns=[Decimal(str(x)) for x in structured_data['performance']['daily_returns']],
            tracking_dates=[date.fromisoformat(d) for d in structured_data['performance']['tracking_dates']],
            # Trading
            total_trades=structured_data['trading']['total_trades'],
            buy_trades=structured_data['trading']['buy_trades'],
            sell_trades=structured_data['trading']['sell_trades'],
            total_fees=Decimal(structured_data['trading']['total_fees']),
            # Redis
            messages_received=structured_data['redis_metrics']['messages_received'],
            messages_processed=structured_data['redis_metrics']['messages_processed'],
            avg_latency_ms=structured_data['redis_metrics']['avg_latency_ms'],
            reconnect_count=structured_data['redis_metrics']['reconnect_count'],
            # Rollovers
            rollovers=structured_data['rollovers']
        )

    def get_summary_text(self) -> str:
        """
        Generate text summary for console display

        Returns:
            Formatted summary string
        """
        lines = []
        lines.append("=" * 60)
        lines.append("PAPER TRADING RESULTS")
        lines.append("=" * 60)
        lines.append(f"Session: {self.start_time} → {self.end_time}")
        lines.append(f"Duration: {self.duration_seconds:.0f}s ({self.duration_seconds/3600:.1f}h)")
        lines.append(f"Mode: {self.mode}")
        lines.append("")

        lines.append("Performance Metrics:")
        lines.append(f"  Initial Capital: {self.initial_capital:,.2f} VND")
        lines.append(f"  Final NAV:       {self.final_nav:,.2f} VND")
        lines.append(f"  HPR:             {self.hpr*100:+.2f}%")
        lines.append(f"  Sharpe Ratio:    {self.sharpe_ratio:.4f}")
        lines.append(f"  Sortino Ratio:   {self.sortino_ratio:.4f}")
        lines.append(f"  Max Drawdown:    {self.max_drawdown*100:.2f}%")
        lines.append("")

        lines.append("Trading Statistics:")
        lines.append(f"  Total Trades:    {self.total_trades}")
        lines.append(f"  Buy Trades:      {self.buy_trades}")
        lines.append(f"  Sell Trades:     {self.sell_trades}")
        lines.append(f"  Total Fees:      {self.total_fees:,.2f} VND")
        lines.append("")

        if self.mode == 'redis':
            lines.append("Redis Statistics:")
            lines.append(f"  Messages Received:  {self.messages_received:,}")
            lines.append(f"  Messages Processed: {self.messages_processed:,}")
            lines.append(f"  Avg Latency:        {self.avg_latency_ms:.2f} ms")
            lines.append(f"  Reconnect Count:    {self.reconnect_count}")
            lines.append("")

        if self.rollovers:
            lines.append(f"Contract Rollovers: {len(self.rollovers)}")
            for rollover in self.rollovers:
                lines.append(f"  {rollover['old_contract']} → {rollover['new_contract']} "
                           f"({rollover['timestamp']})")
            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)

    def print_summary(self):
        """Print summary to console"""
        print(self.get_summary_text())
