import asyncio
import contextlib
import html
import logging
import os

from qara.channels.telegram import TelegramChannel
from qara.config.loader import pid_file_path, socket_path
from qara.config.schema import QaraConfig
from qara.core.bus import NotificationBus
from qara.core.command_handler import CommandHandler
from qara.core.event_engine import EventEngine
from qara.core.events import BaseEvent, ProcessCrashed, ProcessFinished, ProcessStarted
from qara.core.registry import WatcherRegistry
from qara.core.watcher import ProcessWatcher
from qara.storage import log as storage
from qara.transport.server import IPCServer

logger = logging.getLogger(__name__)


class Daemon:
    def __init__(self, config: QaraConfig) -> None:
        self.config = config

        self.engine = EventEngine()
        self.registry = WatcherRegistry()
        self.bus = NotificationBus()
        self.cmd = CommandHandler(config, self.registry)
        self.telegram = TelegramChannel(config.telegram, self.cmd)

        self.bus.register(self.telegram)

        # Plugins subscribe to the engine directly — they receive ALL events
        # including StdoutLine/StderrLine (needed for loss parsing).
        # Subscribed before the bus so on_finish metrics send before cleanup.
        from qara.plugins import load_plugins

        self._plugins = load_plugins(config.plugins.enabled)
        for plugin in self._plugins:
            plugin_cfg = config.plugins.model_dump().get(plugin.name, {})
            if plugin_cfg:
                plugin.configure(plugin_cfg)
        self.engine.subscribe(self._plugin_handler)

        self.engine.subscribe(self.bus.on_event)
        self.engine.subscribe(self._persist_and_cleanup)

        sock = str(socket_path())
        self._ipc = IPCServer(sock, self._handle_ipc)

    async def _persist_and_cleanup(self, event: BaseEvent) -> None:
        if not isinstance(event, (ProcessFinished, ProcessCrashed)):
            return
        self.registry.remove(event.pid)
        record: dict[str, object] = {
            "name": event.name,
            "pid": event.pid,
            "exit_code": event.exit_code,
            "duration_seconds": event.duration_seconds,
            "finished_at": event.timestamp.isoformat(),
        }
        await asyncio.get_running_loop().run_in_executor(None, storage.append_run, record)

    async def _plugin_handler(self, event: BaseEvent) -> None:
        if not self._plugins:
            return
        if isinstance(event, ProcessStarted):
            for plugin in self._plugins:
                await plugin.on_start(event.pid, event.name)
        for plugin in self._plugins:
            await plugin.on_event(event)
        if isinstance(event, (ProcessFinished, ProcessCrashed)):
            for plugin in self._plugins:
                metrics = await plugin.on_finish(event.pid)
                if metrics:
                    lines = [f"📊 <b>{html.escape(plugin.name)} summary</b>"]
                    for k, v in metrics.items():
                        lines.append(f"{html.escape(k)}:\n{html.escape(v)}")
                    await self.telegram.send_text("\n\n".join(lines))

    async def _handle_ipc(self, request: dict[str, object]) -> dict[str, object]:
        req_id = request.get("id", "")
        action = str(request.get("action", ""))
        raw_params = request.get("params")
        params: dict[str, object] = raw_params if isinstance(raw_params, dict) else {}

        if action == "run":
            result = await self._ipc_run(params)
        elif action == "attach":
            result = await self._ipc_attach(params)
        elif action == "restart":
            result = await self._ipc_restart(params)
        else:
            result = await self.cmd.handle(action, params)

        return {"id": req_id, **result}

    async def _ipc_run(self, params: dict[str, object]) -> dict[str, object]:
        argv = params.get("argv")
        if not isinstance(argv, list) or not argv:
            return {"ok": False, "error": "argv must be a non-empty list"}
        name = str(params.get("name") or argv[0])
        cwd_raw = params.get("cwd")
        cwd = cwd_raw if isinstance(cwd_raw, str) else None
        try:
            pid = await self._spawn(argv=argv, name=name, cwd=cwd)
            return {"ok": True, "data": {"pid": pid, "name": name}}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    async def _ipc_attach(self, params: dict[str, object]) -> dict[str, object]:
        pid = params.get("pid")
        if not isinstance(pid, int):
            return {"ok": False, "error": "pid must be an integer"}
        name = str(params.get("name") or pid)
        try:
            await self._attach(pid=pid, name=name)
            return {"ok": True, "data": {"pid": pid, "name": name}}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    async def _ipc_restart(self, params: dict[str, object]) -> dict[str, object]:
        pid_or_name = params.get("pid") or params.get("name")
        entry = self.registry.get(pid_or_name)  # type: ignore[arg-type]
        if not entry:
            return {"ok": False, "error": f"Process '{pid_or_name}' not found"}
        if not entry.watcher.is_spawn_mode:
            return {"ok": False, "error": "Restart is only available for spawned processes"}
        argv = entry.watcher.argv
        name = entry.watcher.name
        cwd = entry.watcher.cwd
        # Kill first, then re-spawn
        await self.cmd.handle("kill", {"pid": entry.watcher.pid})
        await asyncio.sleep(0.5)  # brief pause for cleanup
        try:
            pid = await self._spawn(argv=argv, name=name, cwd=cwd)
            return {"ok": True, "data": {"pid": pid, "name": name}}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    async def _spawn(self, argv: list[str], name: str, cwd: str | None = None) -> int:
        watcher = ProcessWatcher(engine=self.engine, name=name, argv=argv, cwd=cwd)
        task = asyncio.create_task(watcher.run())
        await watcher._started.wait()  # wait until PID is set
        assert watcher.pid is not None
        self.registry.add(watcher, task)
        return watcher.pid

    async def _attach(self, pid: int, name: str) -> None:
        watcher = ProcessWatcher(engine=self.engine, name=name, pid=pid)
        task = asyncio.create_task(watcher.run())
        await watcher._started.wait()
        assert watcher.pid is not None
        self.registry.add(watcher, task)

    async def run_forever(self) -> None:
        """Start the persistent daemon. Blocks until SIGTERM or SIGINT.

        aiogram registers its own SIGTERM/SIGINT handler inside start_polling,
        which stops the polling loop cleanly. We rely on that instead of
        competing with our own signal handler — awaiting polling_task means
        we naturally wake up when aiogram decides to stop.
        """
        pid_file = pid_file_path()
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(os.getpid()))

        for plugin in self._plugins:
            await plugin.setup()

        await self.telegram.start()
        await self._ipc.start()
        logger.info("Daemon started (PID %s)", os.getpid())

        polling_task = asyncio.create_task(self.telegram.start_polling())

        try:
            await polling_task  # aiogram owns SIGTERM; task ends when signal arrives
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("Daemon shutting down...")
            with contextlib.suppress(FileNotFoundError):
                pid_file.unlink()
            watcher_tasks = [e.task for e in self.registry.all_entries()]
            for t in watcher_tasks:
                t.cancel()
            if watcher_tasks:
                await asyncio.gather(*watcher_tasks, return_exceptions=True)
            await self._ipc.stop()
            await self.telegram.stop()

            for plugin in self._plugins:
                await plugin.teardown()

            logger.info("Daemon stopped.")
