import asyncio
import logging
import os
import signal

from qara.config.schema import QaraConfig
from qara.core.registry import WatcherRegistry
from qara.storage.log import tail_runs

logger = logging.getLogger(__name__)


class CommandHandler:
    def __init__(self, config: QaraConfig, registry: WatcherRegistry) -> None:
        self._config = config
        self._registry = registry
    
    async def handle(self, action: str, params: dict[str, object]) -> dict[str, object]:
        method = getattr(self, f"_do_{action}", None)
        if method is None:
            return {"ok": False, "error": f"Unknown action: {action}"}
        try:
            return await method(params)
        except Exception as e:
            logger.exception("Command '%s' raised an exception", action)
            return {"ok": False, "error": str(e)}
        
    async def _do_ping(self, params: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "data": {"pong": True}}
    
    async def _do_status(self, params: dict[str, object]) -> dict[str, object]:
        data = [
            {
                "pid": e.watcher.pid,
                "name": e.watcher.name,
                "mode": "spawn" if e.watcher.is_spawn_mode else "attach",
            }
            for e in self._registry.all_entries()
        ]
        return {"ok": True, "data": data}
    
    async def _do_kill(self, params: dict[str, object]) -> dict[str, object]:
        pid_or_name = params.get("pid") or params.get("name")
        entry = self._registry.get(pid_or_name) # type: ignore[arg-type]
        if not entry or entry.watcher.pid is None:
            return {"ok": False, "error": f"Process '{pid_or_name}' not found"}
        
        pid = entry.watcher.pid
        timeout = self._config.commands.kill_timeout_seconds

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return {"ok": False, "error": f"PID {pid} no longer exists"}
        
        for _ in range(timeout):
            await asyncio.sleep(1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return {"ok": True, "data": {"pid": pid, "signal": "SIGTERM"}}
            
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return {"ok": True, "data": {"pid": pid, "signal": "SIGKILL"}}
    
    async def _do_history(self, params: dict[str, object]) -> dict[str, object]:
        n = int(params.get("limit", 20))  # type: ignore[arg-type]
        return {"ok": True, "data": tail_runs(n)}

    async def _do_logs(self, params: dict[str, object]) -> dict[str, object]:
        pid_or_name = params.get("pid") or params.get("name")
        n = int(params.get("n", 50))  # type: ignore[arg-type]
        entry = self._registry.get(pid_or_name)  # type: ignore[arg-type]
        if not entry:
            return {"ok": False, "error": f"Process '{pid_or_name}' not found"}
        if not entry.watcher.is_spawn_mode:
            return {"ok": False, "error": "Logs unavailable for attached processes"}
        return {"ok": True, "data": entry.watcher.log_tail(n)}

    async def _do_detach(self, params: dict[str, object]) -> dict[str, object]:
        pid_or_name = params.get("pid") or params.get("name")
        entry = self._registry.get(pid_or_name)  # type: ignore[arg-type]
        if not entry:
            return {"ok": False, "error": f"Process '{pid_or_name}' not found"}
        entry.task.cancel()
        return {"ok": True, "data": {"detached": entry.watcher.name}}
