import contextlib
import json
import threading
from pathlib import Path

from platformdirs import user_log_path

_lock = threading.Lock()


def _log_path() -> Path:
    p = user_log_path("qara")
    p.mkdir(parents=True, exist_ok=True)
    return p / "runs.jsonl"


def append_run(record: dict[str, object]) -> None:
    """Append one completed runs as a JSON line.

    Blocking. Must be dispatched via loop.run_in_executor - never called
    directly from async code. Thread-safe via module-level lock.
    """
    with _lock:  # noqa: SIM117
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def tail_runs(n: int = 20) -> list[dict[str, object]]:
    """Return the last n run records, oldest first.

    Reads from EOF in chunks - does not load the full file into memory.
    Malformed JSON lines are skipped silently.
    """

    if n <= 0:
        return []
    path = _log_path()
    if not path.exists():
        return []

    results: list[dict[str, object]] = []
    with path.open("rb") as f:
        f.seek(0, 2)
        remaining = f.tell()
        buf = b""
        while remaining > 0 and len(results) < n:
            chunk_size = min(8192, remaining)
            remaining -= chunk_size
            f.seek(remaining)
            buf = f.read(chunk_size) + buf
            lines = buf.split(b"\n")
            buf = lines[0]  # may be an incomplete line - carry if forward
            for line in reversed(lines[1:]):
                stripped = line.strip()
                if not stripped:
                    continue
                with contextlib.suppress(json.JSONDecodeError):
                    results.append(json.loads(stripped))
                if len(results) == n:
                    break

        # buf holds the first line of the file (remaining == 0 exits the loop before
        # it is processed as a complete line).
        if len(results) < n and buf.strip():
            with contextlib.suppress(json.JSONDecodeError):
                results.append(json.loads(buf))

    return list(reversed(results))
