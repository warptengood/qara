import html
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from qara.channels.base import BaseChannel
from qara.channels.formatting import format_table
from qara.config.schema import TelegramConfig
from qara.core.command_handler import CommandHandler
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


class AuthMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: list[int]) -> None:
        self._allowed = frozenset(allowed_ids)

    async def __call__(  # type: ignore[override]
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        if event.from_user and event.from_user.id not in self._allowed:
            logger.warning("Unauthorized Telegram access from user_id=%s", event.from_user.id)
            return  # silently ignore — no response prevents enumeration
        return await handler(event, data)


class TelegramChannel(BaseChannel):
    def __init__(self, config: TelegramConfig, cmd: CommandHandler) -> None:
        self._config = config
        self._cmd = cmd
        self._bot: Bot | None = None
        self._dp = Dispatcher()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        router = Router()
        router.message.middleware(AuthMiddleware(self._config.allowed_user_ids))

        cmd = self._cmd  # capture for closures

        @router.message(Command("start"))
        async def start_cmd(msg: Message) -> None:
            await msg.answer(
                "👋 <b>qara</b> is watching your processes.\n\nCommands: /status /history /help",
            )

        @router.message(Command("status"))
        async def status_cmd(msg: Message) -> None:
            result = await cmd.handle("status", {})
            if not result["ok"]:
                await msg.answer(f"❌ {result['error']}")
                return
            entries = cast(list[dict[str, object]], result["data"])
            if not entries:
                await msg.answer("No processes currently watched.")
                return
            table = format_table(
                ["PID", "Name", "Mode"],
                [[str(e["pid"]), str(e["name"]), str(e["mode"])] for e in entries],
            )
            await msg.answer(f"📊 <b>Watched Processes</b>\n\n<pre>{html.escape(table)}</pre>")

        @router.message(Command("kill"))
        async def kill_cmd(msg: Message) -> None:
            parts = (msg.text or "").split(maxsplit=1)
            if len(parts) < 2:
                await msg.answer("Usage: /kill &lt;pid_or_name&gt;")
                return
            pid_or_name = parts[1].strip()
            result = await cmd.handle("kill", {"name": pid_or_name})
            if result["ok"]:
                data = cast(dict[str, object], result["data"])
                await msg.answer(f"✅ Killed {data['pid']} via {data['signal']}")
            else:
                await msg.answer(f"❌ {result['error']}")

        @router.message(Command("history"))
        async def history_cmd(msg: Message) -> None:
            parts = (msg.text or "").split(maxsplit=1)
            n = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else 20
            result = await cmd.handle("history", {"limit": n})
            if not result["ok"]:
                await msg.answer(f"❌ {result['error']}")
                return
            runs = cast(list[dict[str, object]], result["data"])
            if not runs:
                await msg.answer("No runs recorded yet.")
                return
            table = format_table(
                ["Name", "Status", "Duration", "Finished"],
                [
                    [
                        str(r.get("name", "?")),
                        "✅" if r.get("exit_code") == 0 else "❌",
                        f"{r.get('duration_seconds', 0):.1f}s",
                        str(r.get("finished_at", ""))[:19],
                    ]
                    for r in runs
                ],
            )
            await msg.answer(f"📜 <b>History</b>\n\n<pre>{html.escape(table)}</pre>")

        @router.message(Command("logs"))
        async def logs_cmd(msg: Message) -> None:
            parts = (msg.text or "").split(maxsplit=2)
            if len(parts) < 2:
                await msg.answer("Usage: /logs &lt;pid_or_name&gt; [n]")
                return
            pid_or_name = parts[1].strip()
            n = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 50
            result = await cmd.handle("logs", {"name": pid_or_name, "n": n})
            if not result["ok"]:
                await msg.answer(f"❌ {result['error']}")
                return
            lines = cast(list[str], result["data"])
            text = "\n".join(lines) if lines else "(no output)"
            await msg.answer(f"<pre>{html.escape(text)}</pre>")

        @router.message(Command("help"))
        async def help_cmd(msg: Message) -> None:
            await msg.answer(
                "/status — list watched processes\n"
                "/kill &lt;pid_or_name&gt; — terminate a process\n"
                "/history [n] — last n completed runs\n"
                "/logs &lt;pid_or_name&gt; [n] — last n output lines\n"
                "/help — this message"
            )

        self._dp.include_router(router)

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

    async def start_polling(self) -> None:
        """Long-running coroutine — run as an asyncio Task."""
        assert self._bot is not None
        await self._dp.start_polling(self._bot)

    async def send(self, event: BaseEvent) -> None:
        text = self._format(event)
        if text is not None:
            await self.send_text(text)

    async def send_text(self, text: str) -> None:
        """Send a raw HTML text message to all allowed users."""
        if not self._bot:
            return
        for user_id in self._config.allowed_user_ids:
            try:
                await self._bot.send_message(chat_id=user_id, text=text)
            except Exception:
                logger.exception("Failed to send message to user %s", user_id)

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
                stderr = f"\n\nStderr tail:\n<pre>{html.escape(event.stderr_tail)}</pre>"
            return (
                f"❌ <b>Process crashed</b>\n"
                f"Name: {name}\n"
                f"PID: {event.pid}\n"
                f"Exit code: {event.exit_code}\n"
                f"Duration: {_fmt_duration(event.duration_seconds)}" + stderr
            )
        return None
