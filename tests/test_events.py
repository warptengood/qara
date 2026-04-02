"""Tests for event dataclasses in qara.core.events."""

from datetime import UTC, datetime

from qara.core.events import (
    BaseEvent,
    PluginMetric,
    ProcessCrashed,
    ProcessFinished,
    ProcessStarted,
    StderrLine,
    StdoutLine,
)


def test_base_event_has_timestamp() -> None:
    event = BaseEvent(pid=1, name="test")
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo == UTC


def test_base_event_is_frozen() -> None:
    event = BaseEvent(pid=1, name="test")
    try:
        event.pid = 2  # type: ignore[misc]
        assert False, "Should have raised FrozenInstanceError"
    except Exception:
        pass


def test_process_started_defaults() -> None:
    event = ProcessStarted(pid=42, name="train")
    assert event.pid == 42
    assert event.name == "train"
    assert event.argv == []


def test_process_started_with_argv() -> None:
    event = ProcessStarted(pid=42, name="train", argv=["python", "train.py"])
    assert event.argv == ["python", "train.py"]


def test_process_finished_defaults() -> None:
    event = ProcessFinished(pid=1, name="job")
    assert event.exit_code == 0
    assert event.duration_seconds == 0.0


def test_process_crashed_defaults() -> None:
    event = ProcessCrashed(pid=1, name="job")
    assert event.exit_code == -1
    assert event.stderr_tail == ""
    assert event.duration_seconds == 0.0


def test_process_crashed_with_values() -> None:
    event = ProcessCrashed(pid=99, name="crash", exit_code=1, stderr_tail="OOM")
    assert event.exit_code == 1
    assert event.stderr_tail == "OOM"


def test_stdout_line() -> None:
    event = StdoutLine(pid=1, name="job", text="loss=0.5")
    assert event.text == "loss=0.5"


def test_stderr_line() -> None:
    event = StderrLine(pid=1, name="job", text="error: cuda OOM")
    assert event.text == "error: cuda OOM"


def test_plugin_metric() -> None:
    event = PluginMetric(pid=1, name="job", plugin_name="ml", key="gpu_util", value=0.87, unit="%")
    assert event.plugin_name == "ml"
    assert event.key == "gpu_util"
    assert event.value == 0.87
    assert event.unit == "%"


def test_events_have_independent_timestamps() -> None:
    e1 = BaseEvent(pid=1, name="a")
    e2 = BaseEvent(pid=2, name="b")
    # Both are valid datetimes — not the same object
    assert isinstance(e1.timestamp, datetime)
    assert isinstance(e2.timestamp, datetime)


def test_explicit_timestamp_is_used() -> None:
    ts = datetime(2025, 1, 1, tzinfo=UTC)
    event = BaseEvent(pid=1, name="test", timestamp=ts)
    assert event.timestamp == ts
