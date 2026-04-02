import asyncio
import logging
import time
from collections import deque

import psutil

from qara.core.event_engine import EventEngine
from qara.core.events import (
    ProcessCrashed,
    ProcessFinished,
    ProcessStarted,
    StderrLine,
    StdoutLine,
)

logger = logging.getLogger(__name__)

LOG_BUFFER_SIZE = 1000


class ProcessWatcher:
    def __init__(
        self,
        engine: EventEngine,
        name: str,
        *,
        argv: list[str] | None = None,
        pid: int | None = None,
    ) -> None:
        if argv is None and pid is None:
            raise ValueError("Provide either argv (spawn mode) or pid (attach mode)")
        if argv is not None and pid is not None:
            raise ValueError("Provide argv OR pid, not both")

        self._engine = engine
        self.name = name
        self.argv = argv or []
        self._attach_pid = pid

        self.pid: int | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._start_time: float | None = None
        self._log_buffer: deque[str] = deque(maxlen=LOG_BUFFER_SIZE)
        self._stderr_lines: list[str] = []

        # Set when PID is known — daemon awaits this before registering in registry
        self._started: asyncio.Event = asyncio.Event()

    @property
    def is_spawn_mode(self) -> bool:
        return bool(self.argv)

    def log_tail(self, n: int = 100) -> list[str]:
        lines = list(self._log_buffer)
        return lines[-n:]

    async def run(self) -> None:
        if self.is_spawn_mode:
            await self._run_spawn()
        else:
            await self._run_attach()

    # ------------------------------------------------------------------
    # Spawn mode
    # ------------------------------------------------------------------

    async def _run_spawn(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            *self.argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.pid = self._process.pid
        self._start_time = time.monotonic()
        self._started.set()  # PID is now known

        await self._engine.publish(ProcessStarted(pid=self.pid, name=self.name, argv=self.argv))

        # Drain stdout and stderr fully before waiting for exit.
        # This guarantees all StdoutLine/StderrLine events are published
        # before ProcessFinished/ProcessCrashed — critical for plugins that
        # accumulate per-line data (e.g. loss tracking).
        await asyncio.gather(
            self._stream_stdout(),
            self._stream_stderr(),
        )
        await self._publish_exit()

    async def _stream_stdout(self) -> None:
        assert self._process and self._process.stdout
        async for raw in self._process.stdout:
            line = raw.decode(errors="replace").rstrip()
            self._log_buffer.append(f"OUT {line}")
            assert self.pid is not None
            await self._engine.publish(StdoutLine(pid=self.pid, name=self.name, text=line))

    async def _stream_stderr(self) -> None:
        assert self._process and self._process.stderr
        async for raw in self._process.stderr:
            line = raw.decode(errors="replace").rstrip()
            self._log_buffer.append(f"ERR {line}")
            self._stderr_lines.append(line)
            assert self.pid is not None
            await self._engine.publish(StderrLine(pid=self.pid, name=self.name, text=line))

    async def _publish_exit(self) -> None:
        assert self._process
        exit_code = self._process.returncode
        if exit_code is None:
            # streams EOF'd but process hasn't exited yet — wait for it
            await self._process.wait()
            exit_code = self._process.returncode
            assert exit_code is not None  # guaranteed after wait()
        duration = time.monotonic() - (self._start_time or 0)
        assert self.pid is not None

        if exit_code == 0:
            await self._engine.publish(
                ProcessFinished(
                    pid=self.pid, name=self.name, exit_code=exit_code, duration_seconds=duration
                )
            )
        else:
            stderr_tail = "\n".join(self._stderr_lines[-20:])
            await self._engine.publish(
                ProcessCrashed(
                    pid=self.pid,
                    name=self.name,
                    exit_code=exit_code,
                    stderr_tail=stderr_tail,
                    duration_seconds=duration,
                )
            )

    # ------------------------------------------------------------------
    # Attach mode
    # ------------------------------------------------------------------

    async def _run_attach(self) -> None:
        pid = self._attach_pid
        assert pid is not None

        self.pid = pid
        self._start_time = time.monotonic()
        self._started.set()  # PID known immediately in attach mode

        if not psutil.pid_exists(pid):
            await self._engine.publish(
                ProcessCrashed(
                    pid=pid,
                    name=self.name,
                    exit_code=-1,
                    stderr_tail="PID not found at attach time",
                )
            )
            return

        await self._engine.publish(ProcessStarted(pid=pid, name=self.name))

        while psutil.pid_exists(pid):
            await asyncio.sleep(1)

        duration = time.monotonic() - (self._start_time or 0)
        await self._engine.publish(
            ProcessFinished(pid=pid, name=self.name, exit_code=0, duration_seconds=duration)
        )
