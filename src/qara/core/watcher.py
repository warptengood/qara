import asyncio
import logging
import os
import socket
import time
from collections import deque
from datetime import datetime, timezone

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

LOG_BUFFER_SIZE = 1000 # max stdout+stderr lines kept per process


class ProcessWatcher:
    """Watches a single process and publishes lifecycle events.

    Spawn mode (qara run): qara forks the process; stdout/stderr are piped.
    Attach Mode (qara attach): qara monitors an existing PID via psutil only.
                                StdoutLine/StderrLine are not emitted.
    """

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
        self._log_buffer: deque[str] = deque(maxlen = LOG_BUFFER_SIZE)

    @property
    def is_spawn_mode(self) -> bool:
        return bool(self.argv)
    
    def log_tail(self, n: int = 100) -> list[str]:
        """Return last n lines from the stdout/stderr ring buffer."""
        lines = list(self._log_buffer)
        return lines[-n:]
    
    async def run(self) -> None:
        """Start watching. Blocks until the process exits."""
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

        await self._engine.publish(ProcessStarted(pid=self.pid, name=self.name, argv=self.argv))

        await asyncio.gather(
            self._stream_stdout(),
            self._stream_stderr(),
            self._wait_for_exit(),
        )

    async def _stream_stdout(self) -> None:
        assert self._process and self._process.stdout
        async for raw in self._process.stdout:
            line = raw.decode(errors="replace").rstrip()
            self._log_buffer.append(f"OUT {line}")
            assert self.pid is not None
            await self._engine.publish(StdoutLine(pid=self.pid, name=self.name, text=line))
    
    async def _stream_stderr(self) -> None:
        assert self._process and self._process.stderr
        stderr_lines: list[str] = []
        async for raw in self._process.stderr:
            line = raw.decode(errors="replace").rstrip()
            self._log_buffer.append(f"ERR {line}")
            stderr_lines.append(line)
            assert self.pid is not None
            await self._engine.publish(StderrLine(pid=self.pid, name=self.name, text=line))
        # Keep reference to full stderr for crash notification
        self._stderr_lines = stderr_lines
    
    async def _wait_for_exit(self) -> None:
        assert self._process
        await self._process.wait()
        exit_code = self._process.returncode
        duration = time.monotonic() - (self._start_time or 0)
        assert self.pid is not None

        if exit_code == 0:
            await self._engine.publish(
                ProcessFinished(
                    pid=self.pid,
                    name=self.name,
                    exit_code=exit_code,
                    duration_seconds=duration,
                )
            )
        else:
            tail_lines = getattr(self, "_stderr_lines", [])[-20:]
            stderr_tail = "\n".join(tail_lines)
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

        # Guard against PID recycling: check the process exists right now
        if not psutil.pid_exists(pid):
            await self._engine.publish(
                ProcessCrashed(pid=self.pid, name=self.name, exit_code=-1, stderr_tail="PID not found")
            )
            return
        
        self.pid = pid
        self._start_time = time.monotonic()
        await self._engine.publish(ProcessStarted(pid=pid, name=self.name))

        # Poll until the process disappears
        while psutil.pid_exists(pid):
            await asyncio.sleep(1)

        duration = time.monotonic() - (self._start_time or 0)

        # psutil can't give us the exit code after the fact
        # Treat disappearance as finished with unknown exit code
        await self._engine.publish(
            ProcessFinished(pid=pid, name=self.name, exit_code=0, duration_seconds=duration)
        )