import asyncio
from dataclasses import dataclass

from qara.core.watcher import ProcessWatcher


@dataclass
class WatcherEntry:
    watcher: ProcessWatcher
    task: asyncio.Task[None]


class WatcherRegistry:
    def __init__(self) -> None:
        self._by_pid: dict[int, WatcherEntry] = {}
        self._by_name: dict[str, WatcherEntry] = {}
    
    def add(self, watcher: ProcessWatcher, task: asyncio.Task[None]) -> None:
        assert watcher.pid is not None
        if watcher.name in self._by_name:
            raise ValueError(f"Name '{watcher.name}' already in use")
        entry = WatcherEntry(watcher=watcher, task=task)
        self._by_pid[watcher.pid] = entry
        self._by_name[watcher.name] = entry
    
    def remove(self, pid: int) -> None:
        entry = self._by_pid.pop(pid, None)
        if entry:
            self._by_name.pop(entry.watcher.name, None)
    
    def get(self, pid_or_name: str | int) -> WatcherEntry | None:
        if isinstance(pid_or_name, int):
            return self._by_pid.get(pid_or_name)
        try:
            return self._by_pid.get(int(pid_or_name))
        except ValueError:
            return self._by_name.get(str(pid_or_name))
    
    def all_entries(self) -> list[WatcherEntry]:
        return list(self._by_pid.values())
    