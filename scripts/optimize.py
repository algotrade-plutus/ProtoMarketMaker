"""
Optimization module
"""

import os
import sys
import numpy as np
from decimal import Decimal
import logging
import optuna
from optuna.samplers import TPESampler

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'src'))
os.chdir(project_root)

from protomarketmaker.config import OPTIMIZATION_CONFIG
from backtesting import Backtesting


class OptunaCallBack:
    """
    Optuna call back class
    """

    def __init__(self) -> None:
        """
        Init optuna callback
        """
        logging.basicConfig(
            filename="result/optimization/optimization.log.csv",
            format="%(message)s",
            filemode="w",
        )
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        self.logger = logger
        self.logger.info("number,step")

    def __call__(self, _: optuna.study.Study, trial: optuna.trial.FrozenTrial) -> None:
        """

        Args:
            study (optuna.study.Study): _description_
            trial (optuna.trial.FrozenTrial): _description_
        """
        step = trial.params["step"]
        self.logger.info(
            "%s,%s,%s",
            trial.number,
            step,
            trial.value,
        )


if __name__ == "__main__":
    data = Backtesting.process_data()

    def objective(trial):
        """
        Sharpe ratio objective function

        Args:
            trial (_type_): _description_

        Returns:
            _type_: _description_
        """
        bt = Backtesting(capital=Decimal("5e5"), printable=False)
        step = trial.suggest_float(
            "step",
            OPTIMIZATION_CONFIG["step"][0],
            OPTIMIZATION_CONFIG["step"][1],
            step=0.1,
        )

        bt.run(data, Decimal(step))

        return bt.metric.sharpe_ratio(risk_free_return=Decimal('0.00023')) * Decimal(
            np.sqrt(250)
        )

    optunaCallBack = OptunaCallBack()
    study = optuna.create_study(
        sampler=TPESampler(seed=OPTIMIZATION_CONFIG["random_seed"]),
        direction="maximize",
    )
    study.optimize(
        objective, n_trials=OPTIMIZATION_CONFIG["no_trials"], callbacks=[optunaCallBack]
    )
