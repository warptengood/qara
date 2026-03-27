from abc import ABC, abstractmethod

from qara.core.events import BaseEvent


class BaseChannel(ABC):
    @abstractmethod
    async def send(self, event: BaseEvent) -> None: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    async def receive_command(self, command: str, params: dict[str, object]) -> None:
        """Override in Phase 3 to handle inbound commands from this channel."""

    