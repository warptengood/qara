import asyncio
import json
import logging
import os
import stat
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, object]], Awaitable[dict[str, object]]]


class IPCServer:
    def __init__(self, socket_path: str, handler: Handler) -> None:
        self._path = socket_path
        self._handler = handler
        self._server: asyncio.AbstractServer | None = None
    
    async def start(self) -> None:
        os.makedirs(os.path.dirname(self._path), mode=0o700, exist_ok=True)
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

        self._server = await asyncio.start_unix_server(
            self._handle_connection, path=self._path
        )
        os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR) # 600
        logger.info("IPC server listening on %s", self._path)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            raw = await reader.readline()
            if not raw:
                return
            request = json.loads(raw.decode())
            response = await self._handler(request)
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        except Exception:
            logger.exception("IPC connection error")
        finally:
            writer.close()
