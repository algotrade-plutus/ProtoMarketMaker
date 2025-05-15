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

FEE_PER_CONTRACT = Decimal(BACKTESTING_CONFIG["fee"]) * Decimal('100')


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

        self.inventory = 0
        self.inventory_price = Decimal('0')

        self.daily_assets: List[Decimal] = [capital]
        self.daily_returns: List[Decimal] = []
        self.tracking_dates = []
        self.daily_inventory = []

        self.old_timestamp = None
        self.bid_price = None
        self.ask_price = None
        self.ac_loss = Decimal("0.0")
        self.total_matched = 0
        self.transactions = []
        self.order_logs = []

    def move_f1_to_f2(self, f1_price, f2_price):
        """
        TODO: move f1 to f2
        """
        if self.inventory > 0:
            self.ac_loss += (self.inventory_price - f1_price) * 100
            self.inventory_price = f2_price
            self.ac_loss += FEE_PER_CONTRACT * abs(self.inventory)
        elif self.inventory < 0:
            self.ac_loss += (f1_price - self.inventory_price) * 100
            self.inventory_price = f2_price
            self.ac_loss += FEE_PER_CONTRACT * abs(self.inventory)

    def update_pnl(self, close_price: Decimal):
        """
        Daily update pnl

        Args:
            close_price (Decimal)
        """
        cur_asset = self.daily_assets[-1]
        new_asset = None
        if self.inventory == 0:
            new_asset = cur_asset - self.ac_loss
        else:
            sign = 1 if self.inventory > 0 else -1
            pnl = (
                sign * abs(self.inventory) * (close_price - self.inventory_price) * 100
                - self.ac_loss
            )
            new_asset = cur_asset + pnl
            print(f"Total matched: {self.total_matched}")
            print(
                f"{round(-self.ac_loss * Decimal('1000'), 2)} - {round((sign * abs(self.inventory) * (close_price - self.inventory_price) * 100 * Decimal('1000')),2)} - {round(pnl * Decimal('1000'), 2)}"
            )
            self.inventory_price = close_price

        self.daily_returns.append(new_asset / self.daily_assets[-1] - 1)
        self.daily_assets.append(new_asset)

    def handle_force_sell(self, price: Decimal):
        """
        Handle force sell

        Args:
            price (Decimal): _description_
        """
        while self.get_maximum_placeable(price) < 0:
            sign = 1 if self.inventory < 0 else -1
            self.inventory += sign
            self.ac_loss += abs(price - self.inventory_price) * 100 + FEE_PER_CONTRACT

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
        return total_placeable - abs(self.inventory)

    def handle_matched_order(self, price):
        """
        Handle matched order

        Args:
            price (_type_): _description_
        """
        matched = 0
        placeable = self.get_maximum_placeable(price)
        if self.bid_price is None or self.ask_price is None:
            return matched

        if self.bid_price >= price and self.inventory >= 0 and placeable > 0:
            self.inventory_price = (
                self.inventory_price * abs(self.inventory) + price
            ) / (abs(self.inventory) + 1)
            self.inventory += 1
            matched += 1
            self.transactions.append([self.cur_date, self.ticker, price, "LONG"])
            self.order_logs.append(
                [self.cur_date, self.ticker, price, "LONG", "FILLED"]
            )
        elif self.bid_price >= price and self.inventory < 0:
            self.ac_loss -= (self.inventory_price - price) * Decimal(
                '100'
            ) - FEE_PER_CONTRACT
            self.inventory += 1
            self.total_matched += 1
            matched -= 1
            self.transactions.append([self.cur_date, self.ticker, price, "LONG"])
            self.order_logs.append(
                [self.cur_date, self.ticker, price, "LONG", "FILLED"]
            )

        if self.ask_price <= price and self.inventory <= 0 and placeable > 0:
            self.inventory_price = (
                self.inventory_price * abs(self.inventory) + price
            ) / (abs(self.inventory) + 1)
            self.inventory -= 1
            matched += 1
            self.transactions.append([self.cur_date, self.ticker, price, "SHORT"])
            self.order_logs.append(
                [self.cur_date, self.ticker, price, "SHORT", "FILLED"]
            )
        elif self.ask_price <= price and self.inventory > 0:
            self.ac_loss -= (price - self.inventory_price) * Decimal(
                '100'
            ) - FEE_PER_CONTRACT
            self.inventory -= 1
            self.total_matched += 1
            matched -= 1
            self.transactions.append([self.cur_date, self.ticker, price, "SHORT"])
            self.order_logs.append(
                [self.cur_date, self.ticker, price, "SHORT", "FILLED"]
            )

        return matched

    def update_bid_ask(self, price: Decimal, step, timestamp):
        """
        Placing bid ask formula

        Args:
            price (Decimal)
        """
        matched = self.handle_matched_order(price)

        if self.old_timestamp is None or timestamp > self.old_timestamp + timedelta(
            seconds=int(BACKTESTING_CONFIG["time"])
        ):
            self.old_timestamp = timestamp
            self.bid_price = price - step * Decimal(max(self.inventory, 0) * 0.02 + 1)
            self.ask_price = price - step * Decimal(min(self.inventory, 0) * 0.02 - 1)
            self.order_logs.append(
                [self.cur_date, self.ticker, self.bid_price, "LONG", "PLACED"]
            )
            self.order_logs.append(
                [self.cur_date, self.ticker, self.ask_price, "SHORT", "PLACED"]
            )
        elif matched != 0:
            self.bid_price = price - step * Decimal(max(self.inventory, 0) * 0.02 + 1)
            self.ask_price = price - step * Decimal(min(self.inventory, 0) * 0.02 - 1)
            self.order_logs.append(
                [self.cur_date, self.ticker, self.bid_price, "LONG", "PLACED"]
            )
            self.order_logs.append(
                [self.cur_date, self.ticker, self.ask_price, "SHORT", "PLACED"]
            )

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
            self.cur_date = row["datetime"]
            self.ticker = row["tickersymbol"]
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
                if self.printable:
                    print("--------------------")
                    print(
                        f"Close: {round(row['close'], 2) if not moving_to_f2 else row['f2_close']} - Avg inv price: {round(self.inventory_price, 2)} - Inventory: {round(self.inventory, 2)}"
                    )
                self.update_pnl(row["f2_close"] if moving_to_f2 else row["close"])
                print(
                    f"Realized asset {row['date']}: {int(self.daily_assets[-1] * Decimal('1000'))} VND"
                )
                moving_to_f2 = False
                self.ac_loss = Decimal("0.0")
                self.bid_price = None
                self.ask_price = None
                self.old_timestamp = None
                self.total_matched = 0

                self.tracking_dates.append(row["date"])
                self.daily_inventory.append(self.inventory)

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
        capital=Decimal("5e5"),
    )

    data = bt.process_data()
    bt.run(data, Decimal("1.8"))

    print(f"Sharpe ratio: {bt.metric.sharpe_ratio(risk_free_return=Decimal('0.06'))}")
    print(f"Sortino ratio: {bt.metric.sortino_ratio(risk_free_return=Decimal('0.06'))}")
    mdd, _ = bt.metric.maximum_drawdown()
    print(f"Maximum drawdown: {mdd}")

    bt.plot_nav()
    bt.plot_drawdown()
    bt.plot_inventory()

    tx_df = pd.DataFrame(
        bt.transactions, columns=["datetime", "tickersymbol", "price", "side"]
    )
    tx_df.to_csv("result/backtest/txs.csv", index=False)

    order_df = pd.DataFrame(
        bt.order_logs, columns=["datetime", "tickersymbol", "price", "side", "status"]
    )
    order_df.to_csv("result/backtest/order_log.csv", index=False)
