"""
Event Recorder

Records all events for debugging and analysis.
"""
import json
from datetime import datetime
from pathlib import Path
from decimal import Decimal
import logging

from protomarketmaker.core import Event, EventType


class EventRecorder:
    """
    Records events to file for replay and analysis

    Writes events to a JSONL (JSON Lines) file where each line
    is a separate JSON object representing one event.

    Example:
        recorder = EventRecorder("logs/events.jsonl")
        recorder.record(event)
        recorder.close()

        # Or use as context manager:
        with EventRecorder("logs/events.jsonl") as recorder:
            recorder.record(event)
    """

    def __init__(self, output_path: str):
        """
        Initialize recorder

        Args:
            output_path: Path to output file (JSONL format)
        """
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_handle = open(self.output_path, 'w')
        self.event_count = 0
        self.logger = logging.getLogger(__name__)

        self.logger.info(f"Event recorder opened: {output_path}")

    def record(self, event: Event):
        """
        Record event to file

        Args:
            event: Event to record
        """
        record = {
            'event_type': event.event_type.value,
            'timestamp': event.timestamp.isoformat(),
            'data': self._serialize_event(event)
        }

        self.file_handle.write(json.dumps(record, default=self._json_serializer) + '\n')
        self.file_handle.flush()
        self.event_count += 1

    def _serialize_event(self, event: Event) -> dict:
        """
        Convert event to dictionary

        Args:
            event: Event to serialize

        Returns:
            Dictionary representation of event
        """
        data = {}
        for key, value in event.__dict__.items():
            if key.startswith('_') or key == 'event_type':
                continue

            # Convert datetime objects
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            # Convert Decimal objects
            elif isinstance(value, Decimal):
                data[key] = float(value)
            # Convert other objects to string
            elif hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool)):
                data[key] = str(value)
            else:
                data[key] = value

        return data

    def _json_serializer(self, obj):
        """
        Custom JSON serializer for special types

        Args:
            obj: Object to serialize

        Returns:
            Serializable representation

        Raises:
            TypeError: If object cannot be serialized
        """
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def close(self):
        """Close recorder and flush remaining events"""
        if self.file_handle and not self.file_handle.closed:
            self.file_handle.close()
            self.logger.info(
                f"Event recorder closed. Recorded {self.event_count} events to {self.output_path}"
            )

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False  # Don't suppress exceptions


class EventReplayer:
    """
    Replays events from a recorded file

    Example:
        replayer = EventReplayer("logs/events.jsonl")
        for event_data in replayer.replay():
            print(event_data)
    """

    def __init__(self, input_path: str):
        """
        Initialize replayer

        Args:
            input_path: Path to JSONL file
        """
        self.input_path = Path(input_path)
        self.logger = logging.getLogger(__name__)

        if not self.input_path.exists():
            raise FileNotFoundError(f"Event file not found: {input_path}")

    def replay(self):
        """
        Replay events from file

        Yields:
            Dictionary with event data
        """
        with open(self.input_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    event_data = json.loads(line.strip())
                    yield event_data
                except json.JSONDecodeError as e:
                    self.logger.error(
                        f"Error parsing line {line_num}: {e}"
                    )
                    continue

    def get_statistics(self) -> dict:
        """
        Get statistics about recorded events

        Returns:
            Dictionary with event counts by type
        """
        stats = {
            'total_events': 0,
            'by_type': {}
        }

        for event_data in self.replay():
            stats['total_events'] += 1
            event_type = event_data.get('event_type', 'UNKNOWN')
            stats['by_type'][event_type] = stats['by_type'].get(event_type, 0) + 1

        return stats
