"""Tests for CommandHandler — all _do_* actions."""

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import qara.storage.log as storage_mod
from qara.config.schema import CommandsConfig, DaemonConfig, QaraConfig, TelegramConfig
from qara.core.command_handler import CommandHandler
from qara.core.event_engine import EventEngine
from qara.core.registry import WatcherRegistry
from qara.core.watcher import ProcessWatcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config() -> QaraConfig:
    return QaraConfig(
        daemon=DaemonConfig(),
        telegram=TelegramConfig(bot_token="x", allowed_user_ids=[]),
        commands=CommandsConfig(kill_timeout_seconds=1),
    )


def _make_watcher(name: str, pid: int, spawn: bool = True) -> ProcessWatcher:
    engine = EventEngine()
    argv = ["python3", "-c", "pass"] if spawn else None
    w = ProcessWatcher(engine=engine, name=name, argv=argv, pid=None if spawn else pid)
    w.pid = pid
    return w


@pytest.fixture
def registry() -> WatcherRegistry:
    return WatcherRegistry()


@pytest.fixture
def handler(registry: WatcherRegistry) -> CommandHandler:
    return CommandHandler(_make_config(), registry)


# ---------------------------------------------------------------------------
# Unknown action
# ---------------------------------------------------------------------------


async def test_unknown_action_returns_error(handler: CommandHandler) -> None:
    result = await handler.handle("nonexistent", {})
    assert result["ok"] is False
    assert "Unknown action" in str(result["error"])


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------


async def test_ping(handler: CommandHandler) -> None:
    result = await handler.handle("ping", {})
    assert result["ok"] is True
    data = cast(dict[str, object], result["data"])
    assert data["pong"] is True


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


async def test_status_empty_registry(handler: CommandHandler) -> None:
    result = await handler.handle("status", {})
    assert result["ok"] is True
    assert cast(list[object], result["data"]) == []


async def test_status_lists_watched_processes(
    handler: CommandHandler, registry: WatcherRegistry
) -> None:
    w = _make_watcher("train", 42)
    task = MagicMock()
    registry.add(w, task)

    result = await handler.handle("status", {})
    assert result["ok"] is True
    data = cast(list[dict[str, object]], result["data"])
    assert len(data) == 1
    assert data[0]["pid"] == 42
    assert data[0]["name"] == "train"
    assert data[0]["mode"] == "spawn"


# ---------------------------------------------------------------------------
# kill
# ---------------------------------------------------------------------------


async def test_kill_unknown_process(handler: CommandHandler) -> None:
    result = await handler.handle("kill", {"name": "ghost"})
    assert result["ok"] is False
    assert "not found" in str(result["error"])


async def test_kill_sends_sigterm_and_returns_ok(
    handler: CommandHandler, registry: WatcherRegistry
) -> None:
    import os
    import signal
    import subprocess

    # Spawn a real process so we have a real PID to kill
    proc = subprocess.Popen(["sleep", "60"])
    w = _make_watcher("sleeper", proc.pid)
    task = MagicMock()
    registry.add(w, task)

    result = await handler.handle("kill", {"name": "sleeper"})
    # Ensure process is cleaned up regardless of test outcome
    proc.wait(timeout=5)

    assert result["ok"] is True
    data = cast(dict[str, object], result["data"])
    assert data["pid"] == proc.pid
    assert data["signal"] in ("SIGTERM", "SIGKILL")


async def test_kill_nonexistent_pid_returns_error(
    handler: CommandHandler, registry: WatcherRegistry
) -> None:
    # Use a watcher whose PID doesn't exist
    w = _make_watcher("ghost", 9999999)
    task = MagicMock()
    registry.add(w, task)

    result = await handler.handle("kill", {"pid": 9999999})
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


async def test_history_returns_runs(
    handler: CommandHandler, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_file = tmp_path / "runs.jsonl"
    monkeypatch.setattr(storage_mod, "_log_path", lambda: log_file)

    from qara.storage.log import append_run

    append_run({"name": "job1", "exit_code": 0})
    append_run({"name": "job2", "exit_code": 1})

    result = await handler.handle("history", {"limit": 10})
    assert result["ok"] is True
    data = cast(list[dict[str, object]], result["data"])
    assert len(data) == 2


async def test_history_default_limit(
    handler: CommandHandler, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_file = tmp_path / "runs.jsonl"
    monkeypatch.setattr(storage_mod, "_log_path", lambda: log_file)

    from qara.storage.log import append_run

    for i in range(5):
        append_run({"name": f"job-{i}"})

    result = await handler.handle("history", {})
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


async def test_logs_unknown_process(handler: CommandHandler) -> None:
    result = await handler.handle("logs", {"name": "ghost"})
    assert result["ok"] is False


async def test_logs_attached_process_returns_error(
    handler: CommandHandler, registry: WatcherRegistry
) -> None:
    # Attach-mode watcher (no argv)
    w = _make_watcher("attached", 777, spawn=False)
    task = MagicMock()
    registry.add(w, task)

    result = await handler.handle("logs", {"name": "attached"})
    assert result["ok"] is False
    assert "unavailable" in str(result["error"]).lower()


async def test_logs_spawn_process_returns_data(
    handler: CommandHandler, registry: WatcherRegistry
) -> None:
    w = _make_watcher("train", 100, spawn=True)
    # Manually push some log lines into the buffer
    w._log_buffer.append("OUT hello")
    w._log_buffer.append("OUT world")
    task = MagicMock()
    registry.add(w, task)

    result = await handler.handle("logs", {"name": "train", "n": 10})
    assert result["ok"] is True
    data = cast(list[str], result["data"])
    assert "OUT hello" in data
    assert "OUT world" in data


# ---------------------------------------------------------------------------
# detach
# ---------------------------------------------------------------------------


async def test_detach_unknown_process(handler: CommandHandler) -> None:
    result = await handler.handle("detach", {"name": "ghost"})
    assert result["ok"] is False


async def test_detach_cancels_task(
    handler: CommandHandler, registry: WatcherRegistry
) -> None:
    w = _make_watcher("train", 50)
    task = MagicMock()
    task.cancel = MagicMock()
    registry.add(w, task)

    result = await handler.handle("detach", {"name": "train"})
    assert result["ok"] is True
    task.cancel.assert_called_once()
    data = cast(dict[str, object], result["data"])
    assert data["detached"] == "train"
