"""
Out-sample evaluation module
"""

from decimal import Decimal
from config.config import BEST_CONFIG
from backtesting import Backtesting


if __name__ == "__main__":
    bt = Backtesting(capital=Decimal('1e6'))

    data = bt.process_data(evaluation=True)
    bt.run(data, Decimal(BEST_CONFIG["step"]))
    bt.plot_nav(path="result/optimization/nav.png")
    bt.plot_drawdown(path="result/optimization/drawdown.png")
    bt.plot_inventory(path="result/optimization/inventory.png")
    print(f"Sharpe ratio: {bt.metric.sharpe_ratio(risk_free_return=Decimal('0.03'))}")
    print(f"Sortino ratio: {bt.metric.sortino_ratio(risk_free_return=Decimal('0.03'))}")
    mdd, _ = bt.metric.maximum_drawdown()
    print(f"Maximum drawdown: {mdd}")
