from abc import ABC, abstractmethod

from qara.core.events import BaseEvent


class BasePlugin(ABC):
    name: str = "unnamed"

    async def setup(self) -> None:
        """Called once at daemon start."""
    
    async def teardown(self) -> None:
        """Called once at daemon shutdown."""
    
    def configure(self, config: dict[str, object]) -> None:
        """Called after construction with the plugin-specific config section."""
    
    @abstractmethod
    async def on_start(self, pid: int, name: str) -> None:
        """Called when a process starts being watched"""
    
    @abstractmethod
    async def on_event(self, event: BaseEvent) -> None:
        """Called for every event - including StdoutLine/StderrLine."""
    
    @abstractmethod
    async def on_finish(self, pid: int) -> dict[str, str]:
        """Called when a process ends.
        Reutrn a dict of a label -> value strings to send as a follow-up
        notifications. Return {} to send nothing.
        """