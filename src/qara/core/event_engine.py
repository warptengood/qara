import logging
from collections.abc import Awaitable, Callable

from qara.core.events import BaseEvent

logger = logging.getLogger(__name__)

Handler = Callable[[BaseEvent], Awaitable[None]]


class EventEngine:
    def __init__(self) -> None:
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> None:
        """Register an async handler to receive all events."""
        self._handlers.append(handler)

    async def publish(self, event: BaseEvent) -> None:
        """Deliver event to all subscribers. Exceptions are logged, not propogated."""
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Event handler %s raised an exception for event %s",
                    handler,
                    event,
                )
