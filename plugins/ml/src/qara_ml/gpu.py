import asyncio
import logging

from qara.core.events import BaseEvent

logger = logging.getLogger(__name__)


class GPUTracker:
    def __init__(self) -> None:
        self._available = False
        self._handles: list = []
        self._poll_interval: int = 5
        self._tasks: dict[int, asyncio.Task] = {}
        self._metrics: dict[int, dict] = {}
    
    def configure(self, poll_interval: int) -> None:
        self._poll_interval = poll_interval
    
    async def init(self) -> None:
        try:
            import pynvml # type: ignore[import]
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            self._handles = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)]
            self._available = True
            logger.info("GPU tracking enabled (%d device(s))", count)
        except Exception:
            logger.warning("pynvml unavailable - GPU tracking disabled")
    
    async def teardown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        if self._available:
            try:
                import pynvml # type: ignore[import]
                pynvml.nvmlShutdown()
            except Exception:
                pass
    
    async def on_start(self, pid: int) -> None:
        if not self._available:
            return
        self._metrics[pid] = {
            "peak_vram_mb": 0.0,
            "util_sum": 0.0,
            "samples": 0,
            "peak_temp": 0,
        }
        self._tasks[pid] = asyncio.create_task(self._poll(pid))
    
    async def on_finish(self, pid: int) -> dict[str, str]:
        task = self._tasks.pop(pid, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        m = self._metrics.pop(pid, None)
        if not m or m["samples"] == 0:
            return {}
        avg_util = m["util_sum"] / m["samples"]
        total_vram_mb = self._total_vram_mb()
        return {
            "GPU summary": (
                f"Peak VRAM: {m['peak_vram_mb']:.0f} MB / {total_vram_mb:0f} MB\n"
                f"Avg GPU util: {avg_util:.0f}%\n"
                f"Peak temp: {m['peak_temp']}°C"
            )
        }
    
    def _total_vram_mb(self) -> float:
        if not self._handles:
            return 0.0
        try:
            import pynvml # type: ignore[import]
            info = pynvml.nvmlDeviceGetMemoryInfo(self._handles[0])
            return info.total / (1024 * 1024)
        except Exception:
            return 0.0
        
    async def _poll(self, pid: int) -> None:
        try:
            import pynvml # type: ignore[import]
            while True:
                await asyncio.sleep(self._poll_interval)
                m = self._metrics.get(pid)
                if m is None:
                    break
                total_util = 0.0
                total_vram_mb = 0.0
                peak_temp = 0
                for handle in self._handles:
                    try:
                        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        temp = pynvml.nvmlDeviceGetTemperature(
                            handle, pynvml.NVML_TEMPERATURE_GPU
                        )
                        total_util += util.gpu
                        total_vram_mb += mem.used / (1024 * 1024)
                        peak_temp = max(peak_temp, temp)
                    except Exception:
                        pass
                m["util_sum"] += total_util / max(len(self._handles), 1)
                m["samples"] += 1
                m["peak_vram_mb"] = max(m["peak_vram_mb"], total_vram_mb)
                m["peak_temp"] = max(m["peak_temp"], peak_temp)
        except asyncio.CancelledError:
            pass