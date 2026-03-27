import html
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from qara.channels.base import BaseChannel
from qara.config.schema import TelegramConfig
from qara.core.events import (
    BaseEvent,
    ProcessCrashed,
    ProcessFinished,
    ProcessStarted,
)

logger = logging.getLogger(__name__)


def _fmt_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}h {m:02d}m {s:02d}s"


class TelegramChannel(BaseChannel):
    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._bot: Bot | None = None

    async def start(self) -> None:
        self._bot = Bot(
            token=self._config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        me = await self._bot.get_me()
        logger.info("Telegram bot connected: @%s", me.username)
    
    async def stop(self) -> None:
        if self._bot:
            await self._bot.session.close()
            self._bot = None
    
    async def send(self, event: BaseEvent) -> None:
        if not self._bot:
            return
        text = self._format(event)
        if text is None:
            return
        for user_id in self._config.allowed_user_ids:
            try:
                await self._bot.send_message(chat_id=user_id, text=text)
            except Exception:
                logger.exception("Failed to send Telegram message to user %s", user_id)
    
    def _format(self, event: BaseEvent) -> str | None:
        n = self._config.notifications
        name = html.escape(event.name)

        if isinstance(event, ProcessStarted) and n.on_start:
            argv_str = html.escape(" ".join(event.argv)) if event.argv else "attached"
            return (
                f"🚀 <b>Process started</b>\n"
                f"Name: {name}\n"
                f"PID: {event.pid}\n"
                f"Command: <code>{argv_str}</code>"
            )
    
        if isinstance(event, ProcessFinished) and n.on_finish:
            return (
                f"✅ <b>Process finished</b>\n"
                f"Name: {name}\n"
                f"PID: {event.pid}\n"
                f"Exit code: {event.exit_code}\n"
                f"Duration: {_fmt_duration(event.duration_seconds)}"
            )

        if isinstance(event, ProcessCrashed) and n.on_crash:
            stderr = ""
            if event.stderr_tail:
                escaped = html.escape(event.stderr_tail)
                stderr = f"\n\nStderr tail:\n<pre>{escaped}</pre>"
            return (
                f"❌ <b>Process crashed</b>\n"
                f"Name: {name}\n"
                f"PID: {event.pid}\n"
                f"Exit code: {event.exit_code}\n"
                f"Duration: {_fmt_duration(event.duration_seconds)}"
                + stderr
            )
        
        return None