"""
Out-sample evaluation module
"""

from decimal import Decimal
import numpy as np
import pandas as pd

import plutus_verify as pv

from proto_market_maker.config.config import BEST_CONFIG
from proto_market_maker.backtest import Backtesting
from proto_market_maker.metrics.metric import get_returns


def main():
    data = Backtesting.process_data(evaluation=True)
    bt = Backtesting(capital=Decimal('5e5'))

    bt.run(data, Decimal(BEST_CONFIG["step"]))
    bt.plot_hpr(path="result/optimization/hpr.svg")
    bt.plot_drawdown(path="result/optimization/drawdown.svg")
    bt.plot_inventory(path="result/optimization/inventory.svg")

    monthly_df = pd.DataFrame(bt.monthly_tracking, columns=["date", "asset"])
    returns = get_returns(monthly_df)

    sharpe = bt.metric.sharpe_ratio(risk_free_return=Decimal('0.00023')) * Decimal(np.sqrt(250))
    sortino = bt.metric.sortino_ratio(risk_free_return=Decimal('0.00023')) * Decimal(np.sqrt(250))
    mdd, _ = bt.metric.maximum_drawdown()

    print(f"HPR {bt.metric.hpr()}")
    print(f"Monthly return {returns['monthly_return']}")
    print(f"Annual return {returns['annual_return']}")
    print(f"Sharpe ratio: {sharpe}")
    print(f"Sortino ratio: {sortino}")
    print(f"Maximum drawdown: {mdd}")

    with pv.step("out_of_sample_backtest") as r:
        r.metric("sharpe_ratio",     float(sharpe),                    unit="ratio")
        r.metric("sortino_ratio",    float(sortino),                   unit="ratio")
        r.metric("maximum_drawdown", float(mdd),                       unit="ratio")
        r.metric("hpr",              float(bt.metric.hpr()),           unit="ratio")
        r.metric("monthly_return",   float(returns['monthly_return']), unit="ratio")
        r.metric("annual_return",    float(returns['annual_return']),  unit="ratio")
        r.artifact("equity_curve",   "result/optimization/hpr.svg",       kind="chart")
        r.artifact("drawdown_chart", "result/optimization/drawdown.svg",  kind="chart")
        r.artifact("inventory",      "result/optimization/inventory.svg", kind="chart")
        r.metadata(seed=2025)


if __name__ == "__main__":
    main()
