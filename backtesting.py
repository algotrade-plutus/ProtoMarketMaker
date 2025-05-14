"""
This is main module for strategy backtesting
"""

import numpy as np
from datetime import timedelta
from decimal import Decimal
from typing import List
import pandas as pd
import matplotlib.pyplot as plt

from config.config import BACKTESTING_CONFIG
from database.data_service import DataService
from metrics.metric import Metric
from utils import (
    get_expired_dates,
    from_cash_to_tradeable_contracts,
)

FEE_PER_POSITION = Decimal(BACKTESTING_CONFIG["fee"]) * Decimal('100') / Decimal('2')


class Backtesting:
    """
    Backtesting main class
    """

    def __init__(
        self,
        capital: Decimal,
        printable=True,
    ):
        """
        Initiate required data

        Args:
            buy_fee (Decimal)
            sell_fee (Decimal)
            from_date_str (str)
            to_date_str (str)
            capital (Decimal)
            path (str, optional). Defaults to "data/is/pe_dps.csv".
            index_path (str, optional). Defaults to "data/is/vnindex.csv".
        """
        self.printable = printable
        self.data_service = DataService()
        self.metric = None

        self.inventory = {"BUY": 0, "SELL": 0}
        self.inventory_price = {"BUY": Decimal('0'), "SELL": Decimal('0')}

        self.daily_assets: List[Decimal] = [capital]
        self.daily_returns: List[Decimal] = []
        self.tracking_dates = []
        self.daily_inventory = []

        self.old_timestamp = None
        self.bid_price = None
        self.ask_price = None
        self.ac_loss = Decimal("0.0")

    def move_f1_to_f2(self, f1_price, f2_price):
        """
        TODO: move f1 to f2
        """
        if self.inventory["BUY"] != 0:
            self.ac_loss += (self.inventory_price["BUY"] - f1_price) * 100
            self.inventory_price["BUY"] = f2_price
            self.ac_loss += FEE_PER_POSITION * self.inventory["BUY"]
        elif self.inventory["SELL"] != 0:
            self.ac_loss += (f1_price - self.inventory_price["SELL"]) * 100
            self.inventory_price["SELL"] = f2_price
            self.ac_loss += FEE_PER_POSITION * self.inventory["SELL"]

    def update_pnl(self, close_price: Decimal):
        """
        Daily update pnl

        Args:
            close_price (Decimal)
        """
        cur_asset = self.daily_assets[-1]
        new_asset = None
        if self.inventory["BUY"] == 0 and self.inventory["SELL"] == 0:
            new_asset = cur_asset - self.ac_loss
        elif self.inventory["BUY"] != 0:
            new_asset = (
                cur_asset
                + self.inventory["BUY"]
                * (close_price - self.inventory_price["BUY"])
                * 100
                - self.ac_loss
            )
            self.inventory_price["BUY"] = close_price
        elif self.inventory["SELL"] != 0:
            new_asset = (
                cur_asset
                + self.inventory["SELL"]
                * (self.inventory_price["SELL"] - close_price)
                * 100
                - self.ac_loss
            )
            self.inventory_price["SELL"] = close_price

        self.daily_returns.append(new_asset / self.daily_assets[-1] - 1)
        self.daily_assets.append(new_asset)

    def handle_force_sell(self, price: Decimal):
        """
        Handle force sell

        Args:
            price (Decimal): _description_
        """
        placeable_sell, placeable_buy = self.get_maximum_placeable(price)

        while placeable_sell < 0:
            placeable_sell, placeable_buy = self.get_maximum_placeable(price)
            self.inventory["SELL"] -= 1
            self.ac_loss += (
                price - self.inventory_price["SELL"]
            ) * 100 + FEE_PER_POSITION

        while placeable_buy < 0:
            placeable_sell, placeable_buy = self.get_maximum_placeable(price)
            self.inventory["BUY"] -= 1
            self.ac_loss += (self.inventory_price["BUY"] - price) * Decimal(
                '100'
            ) + FEE_PER_POSITION

    def get_maximum_placeable(self, inst_price: Decimal):
        """
        Get maximum placeable

        Args:
            inst_price (Decimal): _description_

        Returns:
            _type_: _description_
        """
        total_placeable = max(
            from_cash_to_tradeable_contracts(
                self.daily_assets[-1] - self.ac_loss, inst_price
            ),
            0,
        )
        placeable_sell = max(
            total_placeable + self.inventory["BUY"] - self.inventory["SELL"], 0
        )
        placeable_buy = max(
            total_placeable + self.inventory["SELL"] - self.inventory["BUY"], 0
        )

        return placeable_sell, placeable_buy

    def handle_matched_order(self, price):
        """
        Handle matched order

        Args:
            price (_type_): _description_
        """
        placeable_sell, placeable_buy = self.get_maximum_placeable(price)
        if self.bid_price is None or self.ask_price is None:
            return 0

        matched_side = 0
        if self.bid_price >= price and self.inventory["BUY"] < placeable_buy:
            if self.inventory["SELL"] == 0:
                self.inventory_price["BUY"] = (
                    self.inventory_price["BUY"] * self.inventory["BUY"] + price
                ) / (self.inventory["BUY"] + 1)
                self.inventory["BUY"] += 1
                matched_side += 1
            else:
                self.inventory["SELL"] -= 1
                matched_side -= 1
                self.ac_loss -= (self.inventory_price["SELL"] - price) * Decimal('100')
            self.ac_loss += FEE_PER_POSITION

        if self.ask_price <= price and self.inventory["SELL"] < placeable_sell:
            if self.inventory["BUY"] == 0:
                self.inventory_price["SELL"] = (
                    self.inventory_price["SELL"] * self.inventory["SELL"] + price
                ) / (self.inventory["SELL"] + 1)
                self.inventory["SELL"] += 1
                matched_side -= 1
            else:
                self.inventory["BUY"] -= 1
                matched_side += 1
                self.ac_loss -= (price - self.inventory_price["BUY"]) * Decimal('100')
            self.ac_loss += FEE_PER_POSITION

        return matched_side

    def update_bid_ask(self, price: Decimal, step, timestamp):
        """
        Placing bid ask formula

        Args:
            price (Decimal)
        """
        matched_side = self.handle_matched_order(price)

        if self.old_timestamp is None or timestamp > self.old_timestamp + timedelta(
            seconds=int(BACKTESTING_CONFIG["time"])
        ):
            self.old_timestamp = timestamp
            self.bid_price = price - step * Decimal(self.inventory["BUY"] + 1)
            self.ask_price = price + step * Decimal(self.inventory["SELL"] + 1)
        elif matched_side > 0:
            self.bid_price = price - step * Decimal(self.inventory["BUY"] + 1)
        elif matched_side < 0:
            self.ask_price = price + step * Decimal(self.inventory["SELL"] + 1)

    def process_data(self, evaluation=False):
        prefix_path = "data/os/" if evaluation else "data/is/"
        f1_data = pd.read_csv(f"{prefix_path}VN30F1M_data.csv")
        f1_data["datetime"] = pd.to_datetime(
            f1_data["datetime"], format="%Y-%m-%d %H:%M:%S.%f"
        )
        f1_data["date"] = (
            pd.to_datetime(f1_data["date"], format="%Y-%m-%d").copy().dt.date
        )
        f1_data["close"] = f1_data["close"].apply(Decimal)
        f1_data["price"] = f1_data["price"].apply(Decimal)
        f1_data["best-bid"] = f1_data["best-bid"].apply(Decimal)
        f1_data["best-ask"] = f1_data["best-ask"].apply(Decimal)
        f1_data["spread"] = f1_data["spread"].apply(Decimal)

        f2_data = pd.read_csv(f"{prefix_path}VN30F2M_data.csv")
        f2_data = f2_data[["date", "datetime", "tickersymbol", "price", "close"]].copy()
        f2_data["datetime"] = pd.to_datetime(
            f2_data["datetime"], format="%Y-%m-%d %H:%M:%S.%f"
        )
        f2_data["date"] = (
            pd.to_datetime(f2_data["date"], format="%Y-%m-%d").copy().dt.date
        )
        f2_data.rename(columns={"price": "f2_price", "close": "f2_close"}, inplace=True)
        f2_data["f2_close"] = f2_data["f2_close"].apply(Decimal)
        f2_data["f2_price"] = f2_data["f2_price"].apply(Decimal)

        f1_data = pd.merge(
            f1_data,
            f2_data,
            on=["datetime", "date", "tickersymbol"],
            how="outer",
            sort=True,
        )
        f1_data = f1_data.ffill()
        return f1_data

    def run(self, data: pd.DataFrame, step: Decimal):
        """
        Main backtesting function
        """

        trading_dates = data["date"].unique().tolist()

        start_date = data["datetime"].iloc[0]
        end_date = data["datetime"].iloc[-1]
        expiration_dates = get_expired_dates(start_date, end_date)

        cur_index = 0
        moving_to_f2 = False
        for index, row in data.iterrows():
            if (
                cur_index != len(trading_dates) - 1
                and not expiration_dates.empty()
                and trading_dates[cur_index + 1] >= expiration_dates.queue[0]
            ):
                self.move_f1_to_f2(row["price"], row["f2_price"])
                expiration_dates.get()
                moving_to_f2 = True

            self.handle_force_sell(row["f2_price"] if moving_to_f2 else row["price"])
            self.update_bid_ask(
                row["f2_price"] if moving_to_f2 else row["price"], step, row["datetime"]
            )

            if index == len(data) - 1 or row["date"] != data.iloc[index + 1]["date"]:
                cur_index += 1
                self.update_pnl(row["f2_close"] if moving_to_f2 else row["close"])
                if self.printable:
                    print(
                        f"Realized asset {row['date']}: {int(self.daily_assets[-1] * Decimal('100'))} VND"
                    )
                moving_to_f2 = False
                self.ac_loss = Decimal("0.0")
                self.bid_price = None
                self.ask_price = None
                self.old_timestamp = None

                self.tracking_dates.append(row["date"])
                self.daily_inventory.append(
                    self.inventory["BUY"] - self.inventory["SELL"]
                )

        self.metric = Metric(self.daily_returns, None)

    def plot_nav(self, path="result/backtest/nav.png"):
        """
        Plot and save NAV chart to path

        Args:
            path (str, optional): _description_. Defaults to "result/backtest/nav.png".
        """
        plt.figure(figsize=(10, 6))

        plt.plot(
            self.tracking_dates,
            self.daily_assets[1:],
            label="Portfolio",
            color='black',
        )

        plt.title('Asset Value Over Time')
        plt.xlabel('Time Step')
        plt.ylabel('Asset Value')
        plt.grid(True)
        plt.legend()
        plt.savefig(path, dpi=300, bbox_inches='tight')

    def plot_drawdown(self, path="result/backtest/drawdown.png"):
        """
        Plot and save drawdown chart to path

        Args:
            path (str, optional): _description_. Defaults to "result/backtest/drawdown.png".
        """
        _, drawdowns = self.metric.maximum_drawdown()

        plt.figure(figsize=(10, 6))
        plt.plot(
            self.tracking_dates,
            drawdowns,
            label="Portfolio",
            color='black',
        )

        plt.title('Draw down Value Over Time')
        plt.xlabel('Time Step')
        plt.ylabel('Percentage')
        plt.grid(True)
        plt.savefig(path, dpi=300, bbox_inches='tight')

    def plot_inventory(self, path="result/backtest/inventory.png"):
        plt.figure(figsize=(10, 6))
        plt.plot(
            self.tracking_dates,
            self.daily_inventory,
            label="Portfolio",
            color='black',
        )

        plt.title('Inventory Value Over Time')
        plt.xlabel('Time Step')
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(path, dpi=300, bbox_inches='tight')


if __name__ == "__main__":
    bt = Backtesting(
        capital=Decimal("1.5e7"),
    )

    data = bt.process_data()
    bt.run(data, Decimal("0.8"))

    print(f"Sharpe ratio: {bt.metric.sharpe_ratio(risk_free_return=Decimal('0.03'))}")
    print(f"Sortino ratio: {bt.metric.sortino_ratio(risk_free_return=Decimal('0.03'))}")
    mdd, _ = bt.metric.maximum_drawdown()
    print(f"Maximum drawdown: {mdd}")

    bt.plot_nav()
    bt.plot_drawdown()
    bt.plot_inventory()
