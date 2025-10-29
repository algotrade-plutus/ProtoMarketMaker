"""
Unit tests for HistoricalDataFeed
"""
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path

from core.event import EventBus, EventType
from backtesting.data_feed import HistoricalDataFeed


# Get path to test fixtures
FIXTURES_DIR = Path(__file__).parent / 'fixtures'
SAMPLE_CSV = FIXTURES_DIR / 'sample_data.csv'


class TestHistoricalDataFeed:
    """Test Historical Data Feed"""

    def test_initialization(self):
        """Test data feed initialization"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, str(SAMPLE_CSV))

        assert feed.event_bus is bus
        assert feed.csv_path == str(SAMPLE_CSV)
        assert feed.data is None
        assert feed.events_emitted == 0

    def test_load_data(self):
        """Test loading CSV data"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, str(SAMPLE_CSV))

        data = feed.load_data()

        assert data is not None
        assert len(data) == 20
        assert 'datetime' in data.columns
        assert 'price' in data.columns
        assert feed.data is not None

    def test_load_missing_file(self):
        """Test loading non-existent file"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, 'nonexistent.csv')

        with pytest.raises(FileNotFoundError):
            feed.load_data()

    def test_get_expiration_dates(self):
        """Test expiration date calculation"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, str(SAMPLE_CSV))

        expirations = feed.get_contract_expiration_dates(
            start_date=date(2022, 1, 1),
            end_date=date(2022, 12, 31)
        )

        # Should get 12 expirations (one per month)
        assert len(expirations) == 12

        # First expiration should be 3rd Thursday of January
        # January 2022: 3rd Thursday is Jan 20
        assert expirations[0] == date(2022, 1, 20)

    def test_replay_emits_events(self):
        """Test that replay emits MarketDataEvents"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, str(SAMPLE_CSV))

        # Track received events
        events_received = []

        def on_market_data(event):
            events_received.append(event)

        bus.subscribe(EventType.MARKET_DATA, on_market_data)

        # Load and replay
        feed.load_data()
        feed.replay(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 4),
            show_progress=False
        )

        # Process events
        bus.process_events()

        # Should have received events
        assert len(events_received) > 0
        assert feed.events_emitted > 0

        # Check first event
        first_event = events_received[0]
        assert first_event.contract == 'VN30F1M'
        assert first_event.price == Decimal('1250.0')

    def test_replay_respects_date_range(self):
        """Test that replay only emits events in date range"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, str(SAMPLE_CSV))

        events_received = []
        bus.subscribe(EventType.MARKET_DATA, lambda e: events_received.append(e))

        # Load and replay only Jan 3
        feed.load_data()
        feed.replay(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 3),
            show_progress=False
        )

        bus.process_events()

        # Should only get Jan 3 events (15 events)
        assert len(events_received) == 15

        # All should be from Jan 3
        for event in events_received:
            assert event.timestamp.date() == date(2022, 1, 3)

    def test_get_statistics(self):
        """Test statistics tracking"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, str(SAMPLE_CSV))

        # Before loading
        stats = feed.get_statistics()
        assert stats['data_loaded'] is False
        assert stats['events_emitted'] == 0

        # After loading
        feed.load_data()
        stats = feed.get_statistics()
        assert stats['data_loaded'] is True
        assert stats['total_rows'] == 20

        # After replay
        feed.replay(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 3),
            show_progress=False
        )
        stats = feed.get_statistics()
        assert stats['events_emitted'] > 0

    def test_reset(self):
        """Test resetting statistics"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, str(SAMPLE_CSV))

        feed.load_data()
        feed.replay(
            start_date=date(2022, 1, 3),
            end_date=date(2022, 1, 3),
            show_progress=False
        )

        assert feed.events_emitted > 0

        # Reset
        feed.reset()

        assert feed.events_emitted == 0
        assert feed.expirations_detected == 0

    def test_replay_without_loading(self):
        """Test replay without loading data first"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, str(SAMPLE_CSV))

        with pytest.raises(RuntimeError, match="Data not loaded"):
            feed.replay(
                start_date=date(2022, 1, 3),
                end_date=date(2022, 1, 3)
            )

    def test_replay_no_data_in_range(self):
        """Test replay with no data in date range"""
        bus = EventBus()
        feed = HistoricalDataFeed(bus, str(SAMPLE_CSV))

        feed.load_data()

        with pytest.raises(ValueError, match="No data found"):
            feed.replay(
                start_date=date(2023, 1, 1),
                end_date=date(2023, 1, 31),
                show_progress=False
            )
