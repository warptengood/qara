import logging
import re

from qara.core.events import BaseEvent, StdoutLine

logger = logging.getLogger(__name__)

_DEFAULT_PATTERN = re.compile(
    r"(?i)(?:train_?)?loss[=:\s]+([0-9]+\.?[0-9]*(?:e[-+]?\d+)?)"
)


class LossTracker:
    def __init__(self) -> None:
        self._re = _DEFAULT_PATTERN
        self._stats: dict[int, dict] = {}  # pid → {count, best, best_step, last}

    def configure(self, pattern: str) -> None:
        if not pattern:
            return
        try:
            self._re = re.compile(pattern)
        except re.error:
            logger.warning("Invalid loss_pattern '%s', using default", pattern)

    def on_start(self, pid: int) -> None:
        self._stats[pid] = {"count": 0, "best": float("inf"), "best_step": 0, "last": 0.0}

    def on_event(self, event: BaseEvent) -> None:
        if not isinstance(event, StdoutLine):
            return
        m = self._re.search(event.text)
        if not m:
            return
        try:
            v = float(m.group(1))
        except ValueError:
            return
        s = self._stats.get(event.pid)
        if s is None:
            return
        s["count"] += 1
        s["last"] = v
        if v < s["best"]:
            s["best"] = v
            s["best_step"] = s["count"]

    def on_finish(self, pid: int) -> dict[str, str]:
        s = self._stats.pop(pid, None)
        if not s or s["count"] == 0:
            return {}
        return {
            "Training summary": (
                f"Final loss: {s['last']:.4f}\n"
                f"Best loss: {s['best']:.4f} (step {s['best_step']})"
            )
        }
