from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class EvenType(Enum):
    PROCESS_STARTED = "process_started"
    PROCESS_FINISHED = "process_finished"
    PROCESS_CRASHED = "process_crashed"
    STDOUT_LINE = "stdout_line"
    STDERR_LINE = "stderr_line"
    PLUGIN_METRIC = "plugin_metric"


@dataclass(frozen=True)
class BaseEvent:
    pid: int
    name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ProcessStarted(BaseEvent):
    argv: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessFinished(BaseEvent):
    exit_code: int = 0
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class ProcessCrashed(BaseEvent):
    exit_code: int = -1
    stderr_tail: str = ""
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class StdoutLine(BaseEvent):
    text: str = ""


@dataclass(frozen=True)
class StderrLine(BaseEvent):
    text: str = ""


@dataclass(frozen=True)
class PluginMetric(BaseEvent):
    plugin_name: str = ""
    key: str = ""
    value: float = 0.0
    unit: str = ""

