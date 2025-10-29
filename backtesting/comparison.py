"""
Comparison Utility for Validating Event-Driven Backtest

Compares results from original backtesting.py with event-driven engine
to ensure integrity and correctness.
"""
from decimal import Decimal
from datetime import date
from typing import Dict, Tuple
import logging

from backtesting.engine import BacktestingEngine
from backtesting.results import BacktestResults


class BacktestComparison:
    """
    Compare event-driven backtest with original implementation

    Validates that the new event-driven system produces results
    within acceptable tolerance of the original backtesting.py.
    """

    def __init__(
        self,
        tolerance_sharpe: float = 0.05,  # ±5%
        tolerance_value: float = 0.02,   # ±2%
        tolerance_fees: float = 0.01     # ±1%
    ):
        """
        Initialize comparison utility

        Args:
            tolerance_sharpe: Tolerance for Sharpe ratio (default ±5%)
            tolerance_value: Tolerance for final value (default ±2%)
            tolerance_fees: Tolerance for fees (default ±1%)
        """
        self.tolerance_sharpe = tolerance_sharpe
        self.tolerance_value = tolerance_value
        self.tolerance_fees = tolerance_fees
        self.logger = logging.getLogger(__name__)

    def compare_results(
        self,
        original_results: Dict,
        event_driven_results: BacktestResults
    ) -> Dict:
        """
        Compare original and event-driven results

        Args:
            original_results: Results from original backtesting.py as dict
            event_driven_results: Results from event-driven engine

        Returns:
            Comparison report as dictionary
        """
        report = {
            'metrics': {},
            'passed': True,
            'failures': []
        }

        # Compare Sharpe Ratio
        sharpe_diff = self._compare_metric(
            'sharpe_ratio',
            original_results.get('sharpe_ratio', 0.0),
            event_driven_results.sharpe_ratio,
            self.tolerance_sharpe
        )
        report['metrics']['sharpe_ratio'] = sharpe_diff

        if not sharpe_diff['passed']:
            report['passed'] = False
            report['failures'].append('Sharpe ratio outside tolerance')

        # Compare Final Portfolio Value
        value_diff = self._compare_metric(
            'final_value',
            float(original_results.get('final_capital', 0)),
            float(event_driven_results.final_capital),
            self.tolerance_value
        )
        report['metrics']['final_value'] = value_diff

        if not value_diff['passed']:
            report['passed'] = False
            report['failures'].append('Final value outside tolerance')

        # Compare Total Fees
        fees_diff = self._compare_metric(
            'total_fees',
            float(original_results.get('total_fees', 0)),
            float(event_driven_results.total_fees),
            self.tolerance_fees
        )
        report['metrics']['total_fees'] = fees_diff

        if not fees_diff['passed']:
            report['passed'] = False
            report['failures'].append('Total fees outside tolerance')

        # Compare Trade Count (exact match expected)
        trade_count_original = original_results.get('total_trades', 0)
        trade_count_new = event_driven_results.total_trades

        report['metrics']['total_trades'] = {
            'original': trade_count_original,
            'event_driven': trade_count_new,
            'difference': trade_count_new - trade_count_original,
            'passed': trade_count_original == trade_count_new
        }

        if trade_count_original != trade_count_new:
            self.logger.warning(
                f"Trade count mismatch: original={trade_count_original}, "
                f"event-driven={trade_count_new}"
            )

        return report

    def _compare_metric(
        self,
        name: str,
        original: float,
        event_driven: float,
        tolerance: float
    ) -> Dict:
        """
        Compare a single metric

        Args:
            name: Metric name
            original: Original value
            event_driven: Event-driven value
            tolerance: Acceptable relative difference

        Returns:
            Comparison dictionary
        """
        if original == 0:
            # Avoid division by zero
            difference = abs(event_driven - original)
            relative_diff = 0.0
            passed = difference < 0.01
        else:
            difference = event_driven - original
            relative_diff = abs(difference / original)
            passed = relative_diff <= tolerance

        return {
            'original': original,
            'event_driven': event_driven,
            'difference': difference,
            'relative_difference': relative_diff,
            'tolerance': tolerance,
            'passed': passed
        }

    def generate_report(self, comparison: Dict) -> str:
        """
        Generate human-readable comparison report

        Args:
            comparison: Comparison dictionary from compare_results()

        Returns:
            Formatted report string
        """
        report = ["="*60]
        report.append("BACKTEST INTEGRITY COMPARISON REPORT")
        report.append("="*60)
        report.append("")

        if comparison['passed']:
            report.append("✅ PASSED - Results within tolerance")
        else:
            report.append("❌ FAILED - Results outside tolerance")
            report.append(f"   Failures: {', '.join(comparison['failures'])}")

        report.append("")
        report.append("Detailed Metrics:")
        report.append("-"*60)

        for metric_name, metric_data in comparison['metrics'].items():
            report.append(f"\n{metric_name.upper().replace('_', ' ')}:")
            report.append(f"  Original:       {metric_data['original']:.6f}")
            report.append(f"  Event-Driven:   {metric_data['event_driven']:.6f}")
            report.append(f"  Difference:     {metric_data['difference']:.6f}")

            if 'relative_difference' in metric_data:
                rel_diff = metric_data['relative_difference'] * 100
                report.append(f"  Relative Diff:  {rel_diff:.2f}%")
                report.append(f"  Tolerance:      {metric_data['tolerance']*100:.2f}%")

            status = "✅ PASS" if metric_data['passed'] else "❌ FAIL"
            report.append(f"  Status:         {status}")

        report.append("")
        report.append("="*60)

        return "\n".join(report)

    def run_comparison(
        self,
        csv_path: str,
        start_date: date,
        end_date: date,
        initial_capital: Decimal,
        step: Decimal,
        original_results: Dict
    ) -> Tuple[BacktestResults, Dict]:
        """
        Run event-driven backtest and compare with original

        Args:
            csv_path: Path to CSV data
            start_date: Start date
            end_date: End date
            initial_capital: Initial capital
            step: Strategy step parameter
            original_results: Original backtest results

        Returns:
            Tuple of (event_driven_results, comparison_report)
        """
        self.logger.info("Running event-driven backtest...")

        # Run event-driven backtest
        engine = BacktestingEngine(
            initial_capital=initial_capital,
            step=step,
            csv_path=csv_path
        )

        event_driven_results = engine.run(
            start_date=start_date,
            end_date=end_date,
            show_progress=True
        )

        self.logger.info("Comparing results...")

        # Compare
        comparison = self.compare_results(original_results, event_driven_results)

        # Generate report
        report_text = self.generate_report(comparison)
        self.logger.info(f"\n{report_text}")

        return event_driven_results, comparison
