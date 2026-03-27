import asyncio
import logging

from qara.channels.telegram import TelegramChannel
from qara.config.schema import QaraConfig
from qara.core.bus import NotificationBus
from qara.core.event_engine import EventEngine
from qara.core.events import BaseEvent, ProcessCrashed, ProcessFinished
from qara.core.watcher import ProcessWatcher
from qara.storage import log as storage

logger = logging.getLogger(__name__)


class Daemon:
    def __init__(self, config: QaraConfig) -> None:
        self.config = config
        self.engine = EventEngine()

        self.bus = NotificationBus()
        self.engine.subscribe(self.bus.on_event)

        self.telegram = TelegramChannel(config.telegram)
        self.bus.register(self.telegram)

        self.engine.subscribe(self._persist_run)

    async def _persist_run(self, event: BaseEvent) -> None:
        if not isinstance(event, (ProcessFinished, ProcessCrashed)):
            return
        record: dict[str, object] = {
            "name": event.name,
            "pid": event.pid,
            "exit_code": event.exit_code,
            "duration_seconds": event.duration_seconds,
            "finished_at": event.timestamp.isoformat(),
        }
        await asyncio.get_running_loop().run_in_executor(None, storage.append_run, record)

    async def start(self) -> None:
        await self.telegram.start()

    async def stop(self) -> None:
        await self.telegram.stop()

    async def run_process(self, argv: list[str], name: str) -> None:
        await self.start()
        try:
            watcher = ProcessWatcher(engine=self.engine, name=name, argv=argv)
            await watcher.run()
        finally:
            await self.stop()
    
    async def attach_process(self, pid: int, name: str) -> None:
        await self.start()
        try:
            watcher = ProcessWatcher(engine=self.engine, name=name, pid=pid)
            await watcher.run()
        finally:
            await self.stop()