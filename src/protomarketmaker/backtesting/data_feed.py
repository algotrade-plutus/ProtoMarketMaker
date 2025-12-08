"""
Historical Data Feed

Loads historical CSV data and emits MarketDataEvents in chronological order.
Handles contract expiration detection and rolling.
"""
import pandas as pd
from decimal import Decimal
from datetime import datetime, date
from typing import Optional
import logging
from dateutil.rrule import rrule, MONTHLY, TH
from tqdm import tqdm

from protomarketmaker.core import EventBus, MarketDataEvent, EventType


class HistoricalDataFeed:
    """
    Load and replay historical market data as events

    Features:
    - Loads VN30F1M and VN30F2M data from CSV
    - Merges data on timestamp
    - Detects contract expiration dates (3rd Thursday)
    - Emits MarketDataEvents in chronological order
    - Progress tracking with tqdm

    Example:
        feed = HistoricalDataFeed(
            event_bus=bus,
            csv_path='data/is/historical.csv'
        )
        feed.load_data()
        feed.replay(
            start_date=date(2022, 1, 1),
            end_date=date(2023, 1, 1),
            show_progress=True
        )
    """

    def __init__(
        self,
        event_bus: EventBus,
        csv_path: str = None,
        f1m_path: str = None,
        f2m_path: str = None
    ):
        """
        Initialize data feed

        Args:
            event_bus: Event bus for publishing events
            csv_path: Path to merged CSV file (deprecated, use f1m_path + f2m_path)
            f1m_path: Path to VN30F1M_data.csv (front month)
            f2m_path: Path to VN30F2M_data.csv (second month)
        """
        self.event_bus = event_bus
        self.csv_path = csv_path
        self.f1m_path = f1m_path
        self.f2m_path = f2m_path
        self.data: Optional[pd.DataFrame] = None
        self.logger = logging.getLogger(__name__)

        # Track statistics
        self.events_emitted = 0
        self.expirations_detected = 0

    def load_data(self) -> pd.DataFrame:
        """
        Load historical data from CSV

        If f1m_path and f2m_path are provided, merges them like original backtest.
        Otherwise, loads from csv_path (merged data).

        Expected CSV columns:
        - datetime: Timestamp (YYYY-MM-DD HH:MM:SS)
        - date: Date only (YYYY-MM-DD)
        - tickersymbol: Contract symbol (VN30F1M or VN30F2M)
        - price: Matched price
        - best-bid: Best bid price
        - best-ask: Best ask price
        - spread: Bid-ask spread
        - close: Closing price (F1M)
        - f2_price: F2M matched price
        - f2_close: F2M closing price

        Returns:
            Loaded DataFrame
        """
        # Load and merge F1M + F2M data (like original backtest)
        if self.f1m_path and self.f2m_path:
            return self.load_and_merge_f1m_f2m()

        # Fall back to merged CSV
        if not self.csv_path:
            raise ValueError("Must provide either csv_path OR (f1m_path + f2m_path)")

        self.logger.info(f"Loading data from {self.csv_path}")

        try:
            # Load CSV
            df = pd.read_csv(self.csv_path)

            # Validate required columns
            required_cols = [
                'datetime', 'date', 'tickersymbol', 'price',
                'best-bid', 'best-ask', 'spread', 'close'
            ]
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                raise ValueError(f"Missing required columns: {missing}")

            # Convert datetime
            df['datetime'] = pd.to_datetime(df['datetime'])
            df['date'] = pd.to_datetime(df['date']).dt.date

            # Forward fill missing values
            df = df.ffill()

            # Sort by datetime
            df = df.sort_values('datetime')
            df = df.reset_index(drop=True)

            self.data = df
            self.logger.info(f"Loaded {len(df)} rows from {df['date'].min()} to {df['date'].max()}")

            return df

        except Exception as e:
            self.logger.error(f"Failed to load data: {e}")
            raise

    def load_and_merge_f1m_f2m(self) -> pd.DataFrame:
        """
        Load and merge F1M + F2M data like original backtest

        Replicates backtesting.py's process_data() logic:
        1. Load VN30F1M_data.csv (front month, full columns)
        2. Load VN30F2M_data.csv (second month, price + close only)
        3. Outer merge on datetime/date/tickersymbol
        4. Forward fill to propagate F2 prices

        This ensures at each timestamp, we have both F1 and F2 prices available
        for accurate rollover calculations.

        Returns:
            Merged DataFrame with F1 and F2 prices
        """
        self.logger.info(f"Loading F1M data from {self.f1m_path}")
        self.logger.info(f"Loading F2M data from {self.f2m_path}")

        # Load F1M data (front month)
        f1_data = pd.read_csv(self.f1m_path)
        f1_data["datetime"] = pd.to_datetime(f1_data["datetime"], format="%Y-%m-%d %H:%M:%S.%f")
        f1_data["date"] = pd.to_datetime(f1_data["date"], format="%Y-%m-%d").dt.date
        f1_data["close"] = f1_data["close"].apply(Decimal)
        f1_data["price"] = f1_data["price"].apply(Decimal)
        f1_data["best-bid"] = f1_data["best-bid"].apply(Decimal)
        f1_data["best-ask"] = f1_data["best-ask"].apply(Decimal)
        f1_data["spread"] = f1_data["spread"].apply(Decimal)

        # Load F2M data (second month)
        f2_data = pd.read_csv(self.f2m_path)
        # Don't include tickersymbol - we want to merge on datetime/date only
        f2_data = f2_data[["date", "datetime", "price", "close"]].copy()
        f2_data["datetime"] = pd.to_datetime(f2_data["datetime"], format="%Y-%m-%d %H:%M:%S.%f")
        f2_data["date"] = pd.to_datetime(f2_data["date"], format="%Y-%m-%d").dt.date
        f2_data.rename(columns={"price": "f2_price", "close": "f2_close"}, inplace=True)
        f2_data["f2_close"] = f2_data["f2_close"].apply(Decimal)
        f2_data["f2_price"] = f2_data["f2_price"].apply(Decimal)

        # Merge F1 and F2 data on datetime and date ONLY (not tickersymbol!)
        # This gives us rows with F1's ticker but BOTH F1 and F2 prices at same timestamp
        merged = pd.merge(
            f1_data,
            f2_data,
            on=["datetime", "date"],
            how="outer",
            sort=True,
        )

        # IMPORTANT: Mark rows that originally had F1M data (before forward fill)
        # We only want to emit market data events for F1M ticks, not F2M-only ticks
        merged['has_f1m_data'] = merged['tickersymbol'].notna()

        # Forward fill to propagate F2 prices when F1 stops
        merged = merged.ffill()

        self.logger.info(f"Merged data: {len(merged)} rows")
        self.logger.info(f"Date range: {merged['date'].min()} to {merged['date'].max()}")

        self.data = merged
        return merged

    def get_contract_expiration_dates(
        self,
        start_date: date,
        end_date: date
    ) -> list[date]:
        """
        Get VN30F1M expiration dates (3rd Thursday of each month)

        Args:
            start_date: Start date for expiration calculation
            end_date: End date for expiration calculation

        Returns:
            List of expiration dates
        """
        # Generate all 3rd Thursdays between dates
        expirations = list(rrule(
            MONTHLY,
            byweekday=TH(3),  # 3rd Thursday
            dtstart=start_date,
            until=end_date
        ))

        # Convert to dates
        expiration_dates = [dt.date() for dt in expirations]

        self.logger.info(f"Found {len(expiration_dates)} expiration dates")

        return expiration_dates

    def replay(
        self,
        start_date: date,
        end_date: date,
        show_progress: bool = True,
        contracts: Optional[list[str]] = None
    ):
        """
        Replay historical data as MarketDataEvents

        Emits events in chronological order. When contract expiration
        is detected, the system will handle it via Portfolio and Strategy.

        Args:
            start_date: Start date for replay
            end_date: End date for replay
            show_progress: Show progress bar (tqdm)
            contracts: List of contracts to replay (default: ['VN30F1M'])
        """
        if self.data is None:
            raise RuntimeError("Data not loaded. Call load_data() first.")

        # If no contracts specified, replay all contracts in the data
        if contracts is None:
            contracts = self.data['tickersymbol'].dropna().unique().tolist()

        # Filter data by date range
        mask = (self.data['date'] >= start_date) & (self.data['date'] <= end_date)
        replay_data = self.data[mask].copy()

        if len(replay_data) == 0:
            raise ValueError(f"No data found between {start_date} and {end_date}")

        self.logger.info(
            f"Replaying {len(replay_data)} events from {start_date} to {end_date}"
        )

        # Get expiration dates and trading dates
        expirations = self.get_contract_expiration_dates(start_date, end_date)
        expiration_set = set(expirations)
        trading_dates = sorted(replay_data['date'].unique().tolist())

        # Track current date for expiration detection
        current_date = None
        current_date_index = -1
        # Track close prices for each contract (for daily settlement)
        daily_close_prices = {}
        # Track if we're using F2 prices after rollover (matches original's moving_to_f2 flag)
        using_f2_prices = False
        # Track if rollover was already processed today
        rollover_processed_today = False
        # Track the current active contract (will be updated on rollover)
        current_contract = None

        # Create progress bar
        iterator = tqdm(
            replay_data.iterrows(),
            total=len(replay_data),
            desc="Replaying data",
            disable=not show_progress
        )

        # Replay each row as event
        for index, row in iterator:
            # Check for new trading day
            row_date = row['date']
            if current_date != row_date and current_date is not None:
                # Publish daily settlement event with close prices
                from protomarketmaker.core.event import TimeEvent
                # Use F2 close if we rolled over, otherwise F1 close
                if using_f2_prices and current_contract and pd.notna(row.get('f2_close')):
                    daily_close_prices[current_contract] = Decimal(str(row['f2_close']))

                settlement_event = TimeEvent(
                    timestamp=row['datetime'].to_pydatetime(),
                    event_name="DAILY_SETTLEMENT",
                    date=row['datetime'].to_pydatetime()
                )
                # Attach close prices to the event (will be used by portfolio)
                settlement_event.close_prices = daily_close_prices.copy()
                self.event_bus.publish(settlement_event)
                self.event_bus.process_events()

                # Reset for new day
                daily_close_prices = {}
                using_f2_prices = False  # Reset at end of day (matches original line 274)
                rollover_processed_today = False

                # Update current date index
                current_date_index += 1
                current_date = row_date
            elif current_date is None:
                current_date = row_date
                current_date_index = 0

            # Check if we need to rollover (matches original lines 250-257)
            # Original: if trading_dates[cur_index + 1] >= expiration_dates.queue[0]
            if (not rollover_processed_today and
                current_date_index < len(trading_dates) - 1 and
                len(expirations) > 0):

                next_trading_date = trading_dates[current_date_index + 1]
                # Sort expirations to get the earliest one >= current_date
                remaining_expirations = [exp for exp in expirations if exp >= current_date]

                if remaining_expirations:
                    next_expiration = min(remaining_expirations)
                    if next_trading_date >= next_expiration:
                        # Rollover detected! Emit rollover event with BOTH prices
                        from protomarketmaker.core.event import RolloverEvent

                        f1_price = Decimal(str(row['price']))
                        f2_price = Decimal(str(row.get('f2_price', 0)))

                        if f2_price > 0:  # Only rollover if F2 price available
                            # Determine contract names
                            old_contract = row['tickersymbol']
                            # F2 contract is next month (increment last 2 digits)
                            # e.g., VN30F2201 -> VN30F2202
                            month_num = int(old_contract[-2:])
                            new_month = (month_num % 12) + 1
                            year = old_contract[-4:-2]
                            if new_month == 1:  # Rolled to next year
                                year = str(int(year) + 1).zfill(2)
                            new_contract = f"{old_contract[:-4]}{year}{str(new_month).zfill(2)}"

                            rollover_event = RolloverEvent(
                                timestamp=row['datetime'].to_pydatetime(),
                                old_contract=old_contract,
                                new_contract=new_contract,
                                old_price=f1_price,
                                new_price=f2_price
                            )

                            self.logger.info(
                                f"Rollover: {old_contract} -> {new_contract} | "
                                f"F1={f1_price} | F2={f2_price} | date={row_date}"
                            )

                            self.event_bus.publish(rollover_event)
                            self.event_bus.process_events()

                            using_f2_prices = True
                            rollover_processed_today = True
                            current_contract = new_contract  # Update active contract
                            self.expirations_detected += 1

            # Create market data event
            # Use F2 prices if we're in rollover mode (matches original lines 259-262)
            if row['tickersymbol'] in contracts:
                # IMPORTANT: Only emit events for rows that originally had F1M data
                # F2M-only rows (has_f1m_data=False) should be skipped before rollover
                # After rollover, using_f2_prices will be True and we'll process all rows
                if not row.get('has_f1m_data', True) and not using_f2_prices:
                    continue

                # Initialize current_contract on first row
                if current_contract is None:
                    current_contract = row['tickersymbol']

                # Select price based on rollover state
                if using_f2_prices and pd.notna(row.get('f2_price')):
                    price_to_use = Decimal(str(row['f2_price']))
                    close_to_use = Decimal(str(row.get('f2_close', row['close'])))
                else:
                    price_to_use = Decimal(str(row['price']))
                    close_to_use = Decimal(str(row['close']))

                # Track close price for daily settlement (use current active contract)
                if pd.notna(close_to_use):
                    daily_close_prices[current_contract] = close_to_use

                event = MarketDataEvent(
                    timestamp=row['datetime'].to_pydatetime(),
                    contract=current_contract,  # Use current active contract (changes after rollover)
                    price=price_to_use,
                    bid=Decimal(str(row['best-bid'])),
                    ask=Decimal(str(row['best-ask'])),
                    spread=Decimal(str(row['spread']))
                )

                # Publish event
                self.event_bus.publish(event)
                self.events_emitted += 1

                # Process events immediately to maintain timing and ordering
                # This allows strategy to react to market data in real-time
                self.event_bus.process_events()

                # Update progress bar description
                if show_progress and self.events_emitted % 100 == 0:
                    iterator.set_postfix({
                        'date': str(row_date),
                        'events': self.events_emitted
                    })

        # Emit final daily settlement for the last day
        if current_date is not None:
            from protomarketmaker.core.event import TimeEvent
            # Use last row's datetime for final settlement timestamp
            final_settlement = TimeEvent(
                timestamp=replay_data.iloc[-1]['datetime'].to_pydatetime(),
                event_name="DAILY_SETTLEMENT",
                date=replay_data.iloc[-1]['datetime'].to_pydatetime()
            )
            # Attach close prices for the final day
            final_settlement.close_prices = daily_close_prices.copy()
            self.event_bus.publish(final_settlement)
            self.event_bus.process_events()

            # Check if last day is an expiration
            if current_date in expiration_set:
                self.logger.info(f"Contract expiration detected on {current_date}")
                self.expirations_detected += 1

        self.logger.info(
            f"Replay complete: {self.events_emitted} events, "
            f"{self.expirations_detected} expirations detected"
        )

    def get_statistics(self) -> dict:
        """Get data feed statistics"""
        stats = {
            'events_emitted': self.events_emitted,
            'expirations_detected': self.expirations_detected,
            'data_loaded': self.data is not None,
        }

        if self.data is not None:
            stats['total_rows'] = len(self.data)
            stats['start_date'] = self.data['date'].min()
            stats['end_date'] = self.data['date'].max()
            stats['contracts'] = self.data['tickersymbol'].unique().tolist()

        return stats

    def reset(self):
        """Reset statistics (useful for testing)"""
        self.events_emitted = 0
        self.expirations_detected = 0
