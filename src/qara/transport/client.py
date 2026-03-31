import asyncio
import json
import uuid


class IPCClient:
    def __init__(self, socket_path: str) -> None:
        self._path = socket_path
    
    async def send(self, action: str, params: dict[str, object] | None = None) -> dict[str, object]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self._path), timeout=10.0
            )
        except (FileNotFoundError, ConnectionRefusedError):
            raise RuntimeError("Daemon is not running. Start it with: qara daemon start")
        except asyncio.TimeoutError:
            raise RuntimeError("Daemon connection timed out")
        
        request = {"id": str(uuid.uuid4()), "action": action, "params": params or {}}
        try:
            writer.write(json.dumps(request).encode() + b"\n")
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), timeout=10.0)
            return json.loads(raw.decode())
        finally:
            writer.close()