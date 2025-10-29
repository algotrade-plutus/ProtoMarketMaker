"""
This is main module for strategy backtesting
"""

import numpy as np
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List
import pandas as pd
import matplotlib.pyplot as plt

from config.config import BACKTESTING_CONFIG
from metrics.metric import get_returns, Metric
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
        self.metric = None

        self.inventory = 0
        self.inventory_price = Decimal('0')

        self.daily_assets: List[Decimal] = [capital]
        self.daily_returns: List[Decimal] = []
        self.tracking_dates = []
        self.daily_inventory = []
        self.monthly_tracking = []

        self.old_timestamp = None
        self.bid_price = None
        self.ask_price = None
        self.ac_loss = Decimal("0.0")
        self.transactions = []
        self.order_logs = []

        # Logging infrastructure
        self.log_file = None
        self.signal_count = 0
        self.fill_count = 0
        self.force_sell_count = 0
        self.rollover_count = 0
        self.tick_count = 0

    def log(self, message: str):
        """Write to log file if logging enabled"""
        if self.log_file:
            self.log_file.write(message + "\n")
            self.log_file.flush()

    def move_f1_to_f2(self, f1_price, f2_price):
        """
        TODO: move f1 to f2
        """
        # Capture state before rollover
        inv_price_before = self.inventory_price
        ac_loss_before = self.ac_loss

        if self.inventory > 0:
            pnl = (self.inventory_price - f1_price) * 100
            self.ac_loss += pnl
            self.inventory_price = f2_price
            fee = FEE_PER_CONTRACT * abs(self.inventory)
            self.ac_loss += fee

            # Log rollover
            self.rollover_count += 1
            self.log(
                f"[ROLLOVER] #{self.rollover_count} | f1_price={f1_price} | f2_price={f2_price} | "
                f"position=LONG | inv={self.inventory} | inv_price_before={inv_price_before:.2f} | "
                f"inv_price_after={self.inventory_price:.2f} | ac_loss_before={ac_loss_before:.2f} | "
                f"ac_loss_after={self.ac_loss:.2f} | pnl_realized={pnl:.2f} | fee={fee:.2f}"
            )
        elif self.inventory < 0:
            pnl = (f1_price - self.inventory_price) * 100
            self.ac_loss += pnl
            self.inventory_price = f2_price
            fee = FEE_PER_CONTRACT * abs(self.inventory)
            self.ac_loss += fee

            # Log rollover
            self.rollover_count += 1
            self.log(
                f"[ROLLOVER] #{self.rollover_count} | f1_price={f1_price} | f2_price={f2_price} | "
                f"position=SHORT | inv={self.inventory} | inv_price_before={inv_price_before:.2f} | "
                f"inv_price_after={self.inventory_price:.2f} | ac_loss_before={ac_loss_before:.2f} | "
                f"ac_loss_after={self.ac_loss:.2f} | pnl_realized={pnl:.2f} | fee={fee:.2f}"
            )
        else:
            # No position to roll
            self.rollover_count += 1
            self.log(
                f"[ROLLOVER] #{self.rollover_count} | f1_price={f1_price} | f2_price={f2_price} | "
                f"position=FLAT | inv=0 | no_position_to_roll"
            )

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
            inv_before = self.inventory
            sign = 1 if self.inventory < 0 else -1
            self.inventory += sign
            loss_added = abs(price - self.inventory_price) * 100 + FEE_PER_CONTRACT
            self.ac_loss += loss_added

            # Log force sell
            self.force_sell_count += 1
            self.log(
                f"[FORCE_SELL] #{self.force_sell_count} | price={price} | "
                f"inv_before={inv_before} | inv_after={self.inventory} | "
                f"loss_added={loss_added:.2f} | ac_loss={self.ac_loss:.2f} | "
                f"reason=MARGIN_CALL"
            )

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

        # BID fill (opening long or covering short)
        if self.bid_price >= price and self.inventory >= 0 and placeable > 0:
            inv_before = self.inventory
            inv_price_before = self.inventory_price
            ac_loss_before = self.ac_loss

            self.inventory_price = (
                self.inventory_price * abs(self.inventory) + price
            ) / (abs(self.inventory) + 1)
            self.inventory += 1
            matched += 1

            # Log fill - opening long
            self.fill_count += 1
            self.log(
                f"[FILL] #{self.fill_count} | side=BID | price={price} | qty=1 | "
                f"inv_before={inv_before} | inv_after={self.inventory} | "
                f"inv_price_before={inv_price_before:.2f} | inv_price_after={self.inventory_price:.2f} | "
                f"ac_loss={self.ac_loss:.2f} | placeable={placeable} | type=OPEN_LONG"
            )

        elif self.bid_price >= price and self.inventory < 0:
            inv_before = self.inventory
            inv_price_before = self.inventory_price
            ac_loss_before = self.ac_loss

            pnl_realized = (self.inventory_price - price) * Decimal('100') - FEE_PER_CONTRACT
            self.ac_loss -= pnl_realized
            self.inventory += 1
            matched -= 1

            # Log fill - covering short
            self.fill_count += 1
            self.log(
                f"[FILL] #{self.fill_count} | side=BID_COVER | price={price} | qty=1 | "
                f"inv_before={inv_before} | inv_after={self.inventory} | "
                f"inv_price_before={inv_price_before:.2f} | inv_price_after={self.inventory_price:.2f} | "
                f"pnl_realized={pnl_realized:.2f} | ac_loss_before={ac_loss_before:.2f} | "
                f"ac_loss_after={self.ac_loss:.2f} | type=COVER_SHORT"
            )

        # ASK fill (opening short or covering long)
        if self.ask_price <= price and self.inventory <= 0 and placeable > 0:
            inv_before = self.inventory
            inv_price_before = self.inventory_price
            ac_loss_before = self.ac_loss

            self.inventory_price = (
                self.inventory_price * abs(self.inventory) + price
            ) / (abs(self.inventory) + 1)
            self.inventory -= 1
            matched += 1

            # Log fill - opening short
            self.fill_count += 1
            self.log(
                f"[FILL] #{self.fill_count} | side=ASK | price={price} | qty=1 | "
                f"inv_before={inv_before} | inv_after={self.inventory} | "
                f"inv_price_before={inv_price_before:.2f} | inv_price_after={self.inventory_price:.2f} | "
                f"ac_loss={self.ac_loss:.2f} | placeable={placeable} | type=OPEN_SHORT"
            )

        elif self.ask_price <= price and self.inventory > 0:
            inv_before = self.inventory
            inv_price_before = self.inventory_price
            ac_loss_before = self.ac_loss

            pnl_realized = (price - self.inventory_price) * Decimal('100') - FEE_PER_CONTRACT
            self.ac_loss -= pnl_realized
            self.inventory -= 1
            matched -= 1

            # Log fill - covering long
            self.fill_count += 1
            self.log(
                f"[FILL] #{self.fill_count} | side=ASK_COVER | price={price} | qty=1 | "
                f"inv_before={inv_before} | inv_after={self.inventory} | "
                f"inv_price_before={inv_price_before:.2f} | inv_price_after={self.inventory_price:.2f} | "
                f"pnl_realized={pnl_realized:.2f} | ac_loss_before={ac_loss_before:.2f} | "
                f"ac_loss_after={self.ac_loss:.2f} | type=COVER_LONG"
            )

        return matched

    def update_bid_ask(self, price: Decimal, step, timestamp):
        """
        Placing bid ask formula

        Args:
            price (Decimal)
        """
        matched = self.handle_matched_order(price)

        # Time-elapsed signal
        if self.old_timestamp is None or timestamp > self.old_timestamp + timedelta(
            seconds=int(BACKTESTING_CONFIG["time"])
        ):
            self.old_timestamp = timestamp
            self.bid_price = (
                price - step * Decimal(max(self.inventory, 0) * 0.02 + 1)
            ).quantize(Decimal("0.0"), rounding=ROUND_HALF_UP)
            self.ask_price = (
                price - step * Decimal(min(self.inventory, 0) * 0.02 - 1)
            ).quantize(Decimal("0.0"), rounding=ROUND_HALF_UP)

            # Log signal - time elapsed
            self.signal_count += 1
            spread = self.ask_price - self.bid_price
            self.log(
                f"[SIGNAL] #{self.signal_count} | time={timestamp} | reason=TIME_ELAPSED | "
                f"market_price={price} | bid={self.bid_price} | ask={self.ask_price} | "
                f"spread={spread} | inventory={self.inventory}"
            )

        # Order-filled signal
        elif matched != 0:
            self.bid_price = (
                price - step * Decimal(max(self.inventory, 0) * 0.02 + 1)
            ).quantize(Decimal("0.0"), rounding=ROUND_HALF_UP)
            self.ask_price = (
                price - step * Decimal(min(self.inventory, 0) * 0.02 - 1)
            ).quantize(Decimal("0.0"), rounding=ROUND_HALF_UP)

            # Log signal - order filled
            self.signal_count += 1
            spread = self.ask_price - self.bid_price
            self.log(
                f"[SIGNAL] #{self.signal_count} | time={timestamp} | reason=ORDER_FILLED | "
                f"market_price={price} | bid={self.bid_price} | ask={self.ask_price} | "
                f"spread={spread} | inventory={self.inventory}"
            )

    @staticmethod
    def process_data(evaluation=False):
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

    def run(self, data: pd.DataFrame, step: Decimal, log_path: str = None):
        """
        Main backtesting function

        Args:
            data: Market data DataFrame
            step: Strategy step parameter
            log_path: Optional path to log file for ground truth logging
        """
        # Initialize logging if path provided
        if log_path:
            self.log_file = open(log_path, 'w')
            self.log(f"# ITERATIVE BACKTEST GROUND TRUTH LOG")
            self.log(f"# =====================================")
            self.log(f"# Start: {data['datetime'].iloc[0]}")
            self.log(f"# End: {data['datetime'].iloc[-1]}")
            self.log(f"# Rows: {len(data):,}")
            self.log(f"# Capital: {self.daily_assets[0]}")
            self.log(f"# Step: {step}")
            self.log(f"# Fee per contract: {FEE_PER_CONTRACT}")
            self.log(f"# Update interval: {BACKTESTING_CONFIG['time']} seconds")
            self.log(f"#")

        trading_dates = data["date"].unique().tolist()

        start_date = data["datetime"].iloc[0]
        end_date = data["datetime"].iloc[-1]
        expiration_dates = get_expired_dates(start_date, end_date)

        if log_path:
            self.log(f"# Trading dates: {len(trading_dates)}")
            self.log(f"# Expiration dates: {list(expiration_dates.queue)}")
            self.log(f"# =====================================\n")

        cur_index = 0
        moving_to_f2 = False
        for index, row in data.iterrows():
            # Log market data context periodically
            if log_path and index % 100 == 0:
                self.tick_count += 1
                self.log(
                    f"[TICK] #{index} | time={row['datetime']} | contract={row['tickersymbol']} | "
                    f"price={row['price']} | bid={row['best-bid']} | ask={row['best-ask']} | "
                    f"spread={row['spread']} | using_f2={moving_to_f2}"
                )
            self.cur_date = row["datetime"]
            self.ticker = row["tickersymbol"]

            # Check for rollover
            if (
                cur_index != len(trading_dates) - 1
                and not expiration_dates.empty()
                and trading_dates[cur_index + 1] >= expiration_dates.queue[0]
            ):
                # Log rollover detection
                if log_path:
                    self.log(
                        f"\n[ROLLOVER_DETECT] | date={row['date']} | time={row['datetime']} | "
                        f"next_trading_date={trading_dates[cur_index + 1]} | "
                        f"expiration={expiration_dates.queue[0]} | condition=TRUE"
                    )

                self.move_f1_to_f2(row["price"], row["f2_price"])
                expiration_dates.get()
                moving_to_f2 = True

            self.handle_force_sell(row["f2_price"] if moving_to_f2 else row["price"])
            self.update_bid_ask(
                row["f2_price"] if moving_to_f2 else row["price"], step, row["datetime"]
            )

            # Daily settlement
            if index == len(data) - 1 or row["date"] != data.iloc[index + 1]["date"]:
                cur_index += 1
                close_price = row["f2_close"] if moving_to_f2 else row["close"]

                # Calculate unrealized PnL before settlement
                if self.inventory != 0:
                    sign = 1 if self.inventory > 0 else -1
                    unrealized_pnl = sign * abs(self.inventory) * (close_price - self.inventory_price) * 100
                else:
                    unrealized_pnl = Decimal('0')

                self.update_pnl(close_price)

                # Log daily settlement
                if log_path:
                    self.log(
                        f"\n[DAILY] | date={row['date']} | close={close_price} | "
                        f"using_f2={moving_to_f2} | nav={self.daily_assets[-1]:.2f} | "
                        f"inventory={self.inventory} | inv_price={self.inventory_price:.2f} | "
                        f"ac_loss={self.ac_loss:.2f} | unrealized_pnl={unrealized_pnl:.2f} | "
                        f"daily_return={self.daily_returns[-1]*100:.4f}%\n"
                    )

                if self.printable:
                    print(
                        f"Realized asset {row['date']}: {int(self.daily_assets[-1] * Decimal('1000'))} VND"
                    )
                if moving_to_f2:
                    self.monthly_tracking.append([row["date"], self.daily_assets[-1]])

                moving_to_f2 = False
                self.ac_loss = Decimal("0.0")
                self.bid_price = None
                self.ask_price = None
                self.old_timestamp = None

                self.tracking_dates.append(row["date"])
                self.daily_inventory.append(self.inventory)

        self.metric = Metric(self.daily_returns, None)

        # Close log file
        if log_path:
            self.log(f"\n# =====================================")
            self.log(f"# BACKTEST COMPLETE")
            self.log(f"# =====================================")
            self.log(f"# Total signals: {self.signal_count}")
            self.log(f"# Total fills: {self.fill_count}")
            self.log(f"# Total force sells: {self.force_sell_count}")
            self.log(f"# Total rollovers: {self.rollover_count}")
            self.log(f"# Final NAV: {self.daily_assets[-1]:.2f}")
            self.log(f"# Final inventory: {self.inventory}")
            self.log(f"# HPR: {(self.daily_assets[-1] / self.daily_assets[0] - 1) * 100:.2f}%")
            self.log_file.close()
            self.log_file = None

    def plot_hpr(self, path="result/backtest/hpr.svg"):
        """
        Plot and save NAV chart to path

        Args:
            path (str, optional): _description_. Defaults to "result/backtest/hpr.svg".
        """
        plt.figure(figsize=(10, 6))

        assets = pd.Series(self.daily_assets)
        ac_return = assets.apply(lambda x: x / assets.iloc[0])
        ac_return = [(val - 1) * 100 for val in ac_return.to_numpy()[1:]]
        plt.plot(
            self.tracking_dates,
            ac_return,
            label="Portfolio",
            color='black',
        )

        plt.title('Holding Period Return Over Time')
        plt.xlabel('Time Step')
        plt.ylabel('Holding Period Return (%)')
        plt.grid(True)
        plt.legend()
        plt.savefig(path, dpi=300, bbox_inches='tight')

    def plot_drawdown(self, path="result/backtest/drawdown.svg"):
        """
        Plot and save drawdown chart to path

        Args:
            path (str, optional): _description_. Defaults to "result/backtest/drawdown.svg".
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

    def plot_inventory(self, path="result/backtest/inventory.svg"):
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

    print(
        f"Sharpe ratio: {bt.metric.sharpe_ratio(risk_free_return=Decimal('0.00023')) * Decimal(np.sqrt(250))}"
    )
    print(
        f"Sortino ratio: {bt.metric.sortino_ratio(risk_free_return=Decimal('0.00023')) * Decimal(np.sqrt(250))}"
    )
    mdd, _ = bt.metric.maximum_drawdown()
    print(f"Maximum drawdown: {mdd}")

    monthly_df = pd.DataFrame(bt.monthly_tracking, columns=["date", "asset"])
    returns = get_returns(monthly_df)

    print(f"HPR {bt.metric.hpr()}")
    print(f"Monthly return {returns['monthly_return']}")
    print(f"Annual return {returns['annual_return']}")

    bt.plot_hpr()
    bt.plot_drawdown()
    bt.plot_inventory()
