import asyncio
import logging

from qara.config.schema import QaraConfig
from qara.core.event_engine import EventEngine
from qara.core.events import BaseEvent, ProcessCrashed, ProcessFinished
from qara.core.watcher import ProcessWatcher
from qara.storage import log as storage

logger = logging.getLogger(__name__)


class Daemon:
    def __init__(self, config: QaraConfig) -> None:
        self.config = config
        self.engine = EventEngine()
        self.engine.subscribe(self._on_event)

    async def _on_event(self, event: BaseEvent) -> None:
        if isinstance(event, (ProcessFinished, ProcessCrashed)):
            await asyncio.get_running_loop().run_in_executor(
                None,
                storage.append_run,
                {
                    "name": event.name,
                    "pid": event.pid,
                    "exit_code": event.exit_code if hasattr(event, "exit_code") else None,
                    "duration_seconds": event.duration_seconds if hasattr(event, "duration_seconds") else None,
                    "finished_at": event.timestamp.isoformat(),
                },
            )

    async def run_process(self, argv: list[str], name: str) -> None:
        watcher = ProcessWatcher(engine=self.engine, name=name, argv=argv)
        await watcher.run()
    
    async def attach_process(self, pid: int, name: str) -> None:
        watcher = ProcessWatcher(engine=self.engine, name=name, pid=pid)
        await watcher.run()