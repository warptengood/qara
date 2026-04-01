from qara.core.events import BaseEvent
from qara.plugins.base import BasePlugin
from qara_ml.gpu import GPUTracker
from qara_ml.loss import LossTracker


class MLPlugin(BasePlugin):
    name = "ml"

    def __init__(self) -> None:
        self._gpu = GPUTracker()
        self._loss = LossTracker()

    def configure(self, config: dict[str, object]) -> None:
        interval = config.get("gpu_poll_interval_seconds")
        if isinstance(interval, int):
            self._gpu.configure(interval)
        pattern = config.get("loss_pattern")
        if isinstance(pattern, str):
            self._loss.configure(pattern)

    async def setup(self) -> None:
        await self._gpu.init()
    
    async def teardown(self) -> None:
        await self._gpu.teardown()

    async def on_start(self, pid: int, name: str) -> None:
        await self._gpu.on_start(pid)
        self._loss.on_start(pid)
    
    async def on_event(self, event: BaseEvent) -> None:
        self._loss.on_event(event) # sync, non-blocking regex match

    async def on_finish(self, pid: int) -> dict[str, str]:
        gpu_metrics = await self._gpu.on_finish(pid)
        loss_metrics = self._loss.on_finish(pid)
        return {**gpu_metrics, **loss_metrics}
