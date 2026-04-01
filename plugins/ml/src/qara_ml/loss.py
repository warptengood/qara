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
        self._losses: dict[int, list[float]] = {}

    def configure(self, pattern: str) -> None:
        if not pattern:
            return
        try:
            self._re = re.compile(pattern)
        except re.error:
            logger.warning("Invalid loss_pattern '%s', using default", pattern)
    
    def on_start(self, pid: int) -> None:
        self._losses[pid] = []

    def on_event(self, event: BaseEvent) -> None:
        if not isinstance(event, StdoutLine):
            return
        m = self._re.search(event.text)
        if m:
            try:
                self._losses.setdefault(event.pid, []).append(float(m.group(1)))
            except ValueError:
                pass
    
    def on_finish(self, pid: int) -> dict[str, str]:
        losses = self._losses.pop(pid, [])
        if not losses:
            return {}
        final = losses[-1]
        best = min(losses)
        best_step = losses.index(best) + 1
        return {
            "Training summary": (
                f"Final loss: {final:.4f}\n"
                f"Best loss: {best:.4f} (step {best_step})"
            )
        }