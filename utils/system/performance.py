import time
import os


class FrameSkipper:
    def __init__(self, target_fps: int = 30):
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps
        self.last_time = time.time()
        self.skipped = 0
        self.processed = 0

    def should_process(self) -> bool:
        now = time.time()
        if now - self.last_time >= self.frame_interval:
            self.last_time = self.last_time + self.frame_interval if self.processed > 0 else now
            self.processed += 1
            return True
        self.skipped += 1
        return False

    def get_stats(self) -> dict:
        total = self.skipped + self.processed
        return {
            "processed": self.processed,
            "skipped": self.skipped,
            "skip_rate": f"{self.skipped / max(total, 1) * 100:.1f}%",
        }


class ResourceMonitor:
    def __init__(self):
        self.process = None

    def get_stats(self) -> dict:
        try:
            import psutil
            if self.process is None:
                self.process = psutil.Process(os.getpid())
            cpu = self.process.cpu_percent(interval=0.1)
            mem = self.process.memory_info().rss / (1024 * 1024)
            return {"cpu_percent": cpu, "memory_mb": mem}
        except ImportError:
            return {"error": "psutil not installed"}
        except Exception as e:
            return {"error": str(e)}
