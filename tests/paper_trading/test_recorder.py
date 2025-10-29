"""
Unit tests for Event Recorder
"""
import pytest
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import tempfile
import json

from paper_trading.recorder import EventRecorder, EventReplayer
from core.event import MarketDataEvent, SignalEvent, OrderEvent
from core.enums import EventType


class TestEventRecorder:
    """Test event recorder functionality"""

    def test_initialization(self):
        """Test recorder initialization"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as f:
            temp_path = f.name

        try:
            recorder = EventRecorder(temp_path)
            assert recorder.event_count == 0
            assert recorder.output_path == Path(temp_path)
            recorder.close()
        finally:
            Path(temp_path).unlink()

    def test_record_market_data_event(self):
        """Test recording market data event"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as f:
            temp_path = f.name

        try:
            with EventRecorder(temp_path) as recorder:
                event = MarketDataEvent(
                    timestamp=datetime(2025, 1, 1, 10, 0, 0),
                    contract="VN30F1M",
                    price=Decimal("1250"),
                    bid=Decimal("1249"),
                    ask=Decimal("1251"),
                    spread=Decimal("2")
                )

                recorder.record(event)

            # Verify file contains event
            with open(temp_path, 'r') as f:
                lines = f.readlines()
                assert len(lines) == 1

                event_data = json.loads(lines[0])
                assert event_data['event_type'] == 'MARKET_DATA'
                assert event_data['data']['contract'] == 'VN30F1M'
                assert event_data['data']['price'] == 1250.0
        finally:
            Path(temp_path).unlink()

    def test_record_multiple_events(self):
        """Test recording multiple events"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as f:
            temp_path = f.name

        try:
            with EventRecorder(temp_path) as recorder:
                # Record 3 events
                for i in range(3):
                    event = MarketDataEvent(
                        timestamp=datetime(2025, 1, 1, 10, i, 0),
                        contract="VN30F1M",
                        price=Decimal(str(1250 + i)),
                        bid=Decimal(str(1249 + i)),
                        ask=Decimal(str(1251 + i)),
                        spread=Decimal("2")
                    )
                    recorder.record(event)

            # Verify file contains 3 lines
            with open(temp_path, 'r') as f:
                lines = f.readlines()
                assert len(lines) == 3
        finally:
            Path(temp_path).unlink()

    def test_record_signal_event(self):
        """Test recording signal event"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as f:
            temp_path = f.name

        try:
            with EventRecorder(temp_path) as recorder:
                event = SignalEvent(
                    timestamp=datetime(2025, 1, 1, 10, 0, 0),
                    contract="VN30F1M",
                    signal_type="UPDATE_BID_ASK",
                    bid_price=Decimal("1247.1"),
                    ask_price=Decimal("1252.9"),
                    reason="INITIAL"
                )

                recorder.record(event)

            # Verify
            with open(temp_path, 'r') as f:
                event_data = json.loads(f.readline())
                assert event_data['event_type'] == 'SIGNAL'
                assert event_data['data']['signal_type'] == 'UPDATE_BID_ASK'
                assert event_data['data']['reason'] == 'INITIAL'
        finally:
            Path(temp_path).unlink()

    def test_context_manager(self):
        """Test using recorder as context manager"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as f:
            temp_path = f.name

        try:
            with EventRecorder(temp_path) as recorder:
                event = MarketDataEvent(
                    timestamp=datetime(2025, 1, 1, 10, 0, 0),
                    contract="VN30F1M",
                    price=Decimal("1250"),
                    bid=Decimal("1249"),
                    ask=Decimal("1251"),
                    spread=Decimal("2")
                )
                recorder.record(event)
                # File should auto-close on exit

            # Verify file is closed and readable
            assert Path(temp_path).exists()
        finally:
            Path(temp_path).unlink()


class TestEventReplayer:
    """Test event replayer functionality"""

    def test_replay_events(self):
        """Test replaying recorded events"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as f:
            temp_path = f.name

        try:
            # Record events
            with EventRecorder(temp_path) as recorder:
                for i in range(5):
                    event = MarketDataEvent(
                        timestamp=datetime(2025, 1, 1, 10, i, 0),
                        contract="VN30F1M",
                        price=Decimal(str(1250 + i)),
                        bid=Decimal(str(1249 + i)),
                        ask=Decimal(str(1251 + i)),
                        spread=Decimal("2")
                    )
                    recorder.record(event)

            # Replay events
            replayer = EventReplayer(temp_path)
            events = list(replayer.replay())

            assert len(events) == 5
            assert events[0]['event_type'] == 'MARKET_DATA'
            assert events[0]['data']['price'] == 1250.0
            assert events[4]['data']['price'] == 1254.0
        finally:
            Path(temp_path).unlink()

    def test_get_statistics(self):
        """Test getting replay statistics"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as f:
            temp_path = f.name

        try:
            # Record mixed events
            with EventRecorder(temp_path) as recorder:
                # 3 market data events
                for i in range(3):
                    event = MarketDataEvent(
                        timestamp=datetime(2025, 1, 1, 10, i, 0),
                        contract="VN30F1M",
                        price=Decimal("1250"),
                        bid=Decimal("1249"),
                        ask=Decimal("1251"),
                        spread=Decimal("2")
                    )
                    recorder.record(event)

                # 2 signal events
                for i in range(2):
                    event = SignalEvent(
                        timestamp=datetime(2025, 1, 1, 10, i, 0),
                        contract="VN30F1M",
                        signal_type="UPDATE_BID_ASK",
                        bid_price=Decimal("1247.1"),
                        ask_price=Decimal("1252.9"),
                        reason="INITIAL"
                    )
                    recorder.record(event)

            # Get statistics
            replayer = EventReplayer(temp_path)
            stats = replayer.get_statistics()

            assert stats['total_events'] == 5
            assert stats['by_type']['MARKET_DATA'] == 3
            assert stats['by_type']['SIGNAL'] == 2
        finally:
            Path(temp_path).unlink()

    def test_file_not_found(self):
        """Test replayer with non-existent file"""
        with pytest.raises(FileNotFoundError):
            EventReplayer("nonexistent.jsonl")
