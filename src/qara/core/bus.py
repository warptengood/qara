import logging

from qara.channels.base import BaseChannel
from qara.core.events import BaseEvent, StderrLine, StdoutLine

logger = logging.getLogger(__name__)

_INTERNAL_EVENTS = (StdoutLine, StderrLine)


class NotificationBus:
    def __init__(self) -> None:
        self._channels: list[BaseChannel] = []

    def register(self, channel: BaseChannel) -> None:
        self._channels.append(channel)

    async def on_event(self, event: BaseEvent) -> None:
        if isinstance(event, _INTERNAL_EVENTS):
            return # never forwarded to channels
        
        for channel in self._channels:
            try:
                await channel.send(event)
            except Exception:
                logger.exception(
                    "Channel %s failed to send event %s", channel.__class__.__name__, event
                )