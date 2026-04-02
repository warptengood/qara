"""Tests for JSONL append log — append_run and tail_runs."""

from pathlib import Path
from unittest.mock import patch

import pytest

import qara.storage.log as storage_mod
from qara.storage.log import append_run, tail_runs


def _patch_log_path(tmp_path: Path) -> Path:
    """Return a temporary JSONL path and patch _log_path to use it."""
    return tmp_path / "runs.jsonl"


@pytest.fixture(autouse=True)
def isolated_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the log to a temp file for every test."""
    log_file = tmp_path / "runs.jsonl"
    monkeypatch.setattr(storage_mod, "_log_path", lambda: log_file)
    return log_file


def test_tail_runs_empty_when_no_file() -> None:
    assert tail_runs() == []


def test_append_and_tail_single_record() -> None:
    record: dict[str, object] = {"name": "train", "pid": 1, "exit_code": 0}
    append_run(record)
    results = tail_runs(n=10)
    assert results == [record]


def test_append_multiple_and_tail_all() -> None:
    records = [{"name": f"job-{i}", "pid": i, "exit_code": 0} for i in range(5)]
    for r in records:
        append_run(r)
    results = tail_runs(n=10)
    assert results == records


def test_tail_respects_n_limit() -> None:
    for i in range(10):
        append_run({"name": f"job-{i}", "pid": i})
    results = tail_runs(n=3)
    assert len(results) == 3
    # Should be the LAST 3 records, oldest-first
    assert results[0]["name"] == "job-7"
    assert results[2]["name"] == "job-9"


def test_tail_zero_returns_empty() -> None:
    append_run({"name": "job", "pid": 1})
    assert tail_runs(n=0) == []


def test_tail_more_than_available() -> None:
    append_run({"name": "only", "pid": 1})
    results = tail_runs(n=100)
    assert len(results) == 1


def test_append_preserves_all_fields() -> None:
    record: dict[str, object] = {
        "name": "gpu_train",
        "pid": 42,
        "exit_code": 1,
        "duration_seconds": 3600.5,
        "finished_at": "2025-01-01T00:00:00+00:00",
    }
    append_run(record)
    results = tail_runs(n=1)
    assert results[0] == record


def test_malformed_lines_are_skipped(isolated_log: Path) -> None:
    # Write a valid record, then a broken JSON line, then another valid one
    isolated_log.write_text(
        '{"name": "good1", "pid": 1}\nNOT_JSON\n{"name": "good2", "pid": 2}\n',
        encoding="utf-8",
    )
    results = tail_runs(n=10)
    names = [r["name"] for r in results]
    assert "good1" in names
    assert "good2" in names
    assert len(results) == 2


def test_order_is_oldest_first() -> None:
    for i in range(3):
        append_run({"seq": i})
    results = tail_runs(n=10)
    seqs = [r["seq"] for r in results]
    assert seqs == [0, 1, 2]
