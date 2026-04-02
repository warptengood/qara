"""Tests for WatcherRegistry — add, remove, get by pid/name."""

import asyncio
from unittest.mock import MagicMock

import pytest

from qara.core.event_engine import EventEngine
from qara.core.registry import WatcherRegistry
from qara.core.watcher import ProcessWatcher


def _make_watcher(name: str, pid: int) -> ProcessWatcher:
    engine = EventEngine()
    w = ProcessWatcher(engine=engine, name=name, argv=["sleep", "60"])
    w.pid = pid  # set pid manually — avoids spawning a real process
    return w


def _make_task() -> asyncio.Task[None]:  # type: ignore[type-arg]
    """Return a cancelled dummy Task to satisfy the registry's type requirement."""
    loop = asyncio.new_event_loop()
    coro = asyncio.sleep(0)
    task: asyncio.Task[None] = loop.create_task(coro)
    loop.close()
    return task


@pytest.fixture
def registry() -> WatcherRegistry:
    return WatcherRegistry()


def test_add_and_get_by_pid(registry: WatcherRegistry) -> None:
    w = _make_watcher("train", 123)
    task = MagicMock(spec=asyncio.Task)
    registry.add(w, task)

    entry = registry.get(123)
    assert entry is not None
    assert entry.watcher is w


def test_add_and_get_by_name(registry: WatcherRegistry) -> None:
    w = _make_watcher("train", 123)
    task = MagicMock(spec=asyncio.Task)
    registry.add(w, task)

    entry = registry.get("train")
    assert entry is not None
    assert entry.watcher is w


def test_get_by_pid_string(registry: WatcherRegistry) -> None:
    """get("123") should resolve to the entry with pid 123."""
    w = _make_watcher("train", 123)
    task = MagicMock(spec=asyncio.Task)
    registry.add(w, task)

    entry = registry.get("123")
    assert entry is not None
    assert entry.watcher.pid == 123


def test_get_missing_returns_none(registry: WatcherRegistry) -> None:
    assert registry.get(999) is None
    assert registry.get("nope") is None


def test_remove_clears_both_indices(registry: WatcherRegistry) -> None:
    w = _make_watcher("train", 42)
    task = MagicMock(spec=asyncio.Task)
    registry.add(w, task)
    registry.remove(42)

    assert registry.get(42) is None
    assert registry.get("train") is None


def test_remove_nonexistent_is_noop(registry: WatcherRegistry) -> None:
    registry.remove(9999)  # should not raise


def test_duplicate_name_raises(registry: WatcherRegistry) -> None:
    w1 = _make_watcher("train", 10)
    w2 = _make_watcher("train", 11)
    task = MagicMock(spec=asyncio.Task)
    registry.add(w1, task)
    with pytest.raises(ValueError, match="already in use"):
        registry.add(w2, task)


def test_all_entries_returns_all(registry: WatcherRegistry) -> None:
    for pid in [10, 20, 30]:
        w = _make_watcher(f"job-{pid}", pid)
        task = MagicMock(spec=asyncio.Task)
        registry.add(w, task)

    entries = registry.all_entries()
    assert len(entries) == 3
    pids = {e.watcher.pid for e in entries}
    assert pids == {10, 20, 30}


def test_all_entries_empty(registry: WatcherRegistry) -> None:
    assert registry.all_entries() == []
