"""Tests for ProcessWatcher — spawn mode with real subprocesses."""

import asyncio

import pytest

from qara.core.event_engine import EventEngine
from qara.core.events import (
    BaseEvent,
    ProcessCrashed,
    ProcessFinished,
    ProcessStarted,
    StderrLine,
    StdoutLine,
)
from qara.core.watcher import ProcessWatcher


async def _run_and_collect(argv: list[str], name: str = "test") -> list[BaseEvent]:
    """Spawn a watcher, run it to completion, return all published events."""
    engine = EventEngine()
    events: list[BaseEvent] = []

    async def capture(event: BaseEvent) -> None:
        events.append(event)

    engine.subscribe(capture)
    watcher = ProcessWatcher(engine=engine, name=name, argv=argv)
    await watcher.run()
    return events


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_constructor_requires_argv_or_pid() -> None:
    engine = EventEngine()
    with pytest.raises(ValueError, match="argv.*pid"):
        ProcessWatcher(engine=engine, name="x")


def test_constructor_rejects_both_argv_and_pid() -> None:
    engine = EventEngine()
    with pytest.raises(ValueError, match="not both"):
        ProcessWatcher(engine=engine, name="x", argv=["echo"], pid=1)


# ---------------------------------------------------------------------------
# Spawn mode — successful exit
# ---------------------------------------------------------------------------


async def test_spawn_success_publishes_started_and_finished() -> None:
    events = await _run_and_collect(["python3", "-c", "print('hello')"])

    types = [type(e) for e in events]
    assert ProcessStarted in types
    assert ProcessFinished in types
    assert ProcessCrashed not in types


async def test_spawn_stdout_captured() -> None:
    events = await _run_and_collect(["python3", "-c", "print('hello world')"])

    stdout_events = [e for e in events if isinstance(e, StdoutLine)]
    assert any("hello world" in e.text for e in stdout_events)


async def test_spawn_stderr_captured() -> None:
    events = await _run_and_collect(
        ["python3", "-c", "import sys; sys.stderr.write('err msg\\n')"]
    )
    stderr_events = [e for e in events if isinstance(e, StderrLine)]
    assert any("err msg" in e.text for e in stderr_events)


async def test_spawn_finished_exit_code_zero() -> None:
    events = await _run_and_collect(["python3", "-c", "pass"])
    finished = next(e for e in events if isinstance(e, ProcessFinished))
    assert finished.exit_code == 0


async def test_spawn_finished_has_positive_duration() -> None:
    events = await _run_and_collect(["python3", "-c", "pass"])
    finished = next(e for e in events if isinstance(e, ProcessFinished))
    assert finished.duration_seconds >= 0.0


# ---------------------------------------------------------------------------
# Spawn mode — failed exit
# ---------------------------------------------------------------------------


async def test_spawn_crash_publishes_crashed() -> None:
    events = await _run_and_collect(["python3", "-c", "raise SystemExit(1)"])
    types = [type(e) for e in events]
    assert ProcessCrashed in types
    assert ProcessFinished not in types


async def test_spawn_crash_exit_code() -> None:
    events = await _run_and_collect(["python3", "-c", "raise SystemExit(42)"])
    crashed = next(e for e in events if isinstance(e, ProcessCrashed))
    assert crashed.exit_code == 42


async def test_spawn_crash_stderr_tail_captured() -> None:
    events = await _run_and_collect(
        ["python3", "-c", "import sys; sys.stderr.write('fatal error\\n'); raise SystemExit(1)"]
    )
    crashed = next(e for e in events if isinstance(e, ProcessCrashed))
    assert "fatal error" in crashed.stderr_tail


# ---------------------------------------------------------------------------
# Event ordering
# ---------------------------------------------------------------------------


async def test_started_published_before_finished() -> None:
    events = await _run_and_collect(["python3", "-c", "pass"])
    types = [type(e) for e in events if type(e) in (ProcessStarted, ProcessFinished)]
    assert types.index(ProcessStarted) < types.index(ProcessFinished)


async def test_stdout_lines_before_finished() -> None:
    events = await _run_and_collect(["python3", "-c", "print('line1'); print('line2')"])
    indices = {type(e): i for i, e in enumerate(events)}
    assert indices[StdoutLine] < indices[ProcessFinished]


# ---------------------------------------------------------------------------
# PID and name
# ---------------------------------------------------------------------------


async def test_pid_set_after_run() -> None:
    engine = EventEngine()
    watcher = ProcessWatcher(engine=engine, name="myjob", argv=["python3", "-c", "pass"])
    await watcher.run()
    assert watcher.pid is not None
    assert isinstance(watcher.pid, int)


async def test_event_name_matches_watcher_name() -> None:
    events = await _run_and_collect(["python3", "-c", "pass"], name="my_training_run")
    assert all(e.name == "my_training_run" for e in events)


# ---------------------------------------------------------------------------
# log_tail
# ---------------------------------------------------------------------------


async def test_log_tail_captures_output() -> None:
    engine = EventEngine()
    events: list[BaseEvent] = []

    async def capture(event: BaseEvent) -> None:
        events.append(event)

    engine.subscribe(capture)
    watcher = ProcessWatcher(
        engine=engine, name="t", argv=["python3", "-c", "print('line1'); print('line2')"]
    )
    await watcher.run()

    tail = watcher.log_tail()
    assert any("line1" in line for line in tail)
    assert any("line2" in line for line in tail)


async def test_log_tail_n_limits_output() -> None:
    engine = EventEngine()

    async def noop(event: BaseEvent) -> None:
        pass

    engine.subscribe(noop)
    script = "for i in range(10): print(i)"
    watcher = ProcessWatcher(engine=engine, name="t", argv=["python3", "-c", script])
    await watcher.run()

    tail = watcher.log_tail(n=3)
    assert len(tail) == 3
