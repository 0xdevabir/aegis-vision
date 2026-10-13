import re
import time
from typing import Callable, Optional, Set


class LicensePlateRecognizer:
    def __init__(self, languages: list = None, gpu: bool = False):
        self.languages = languages or ["en"]
        self.gpu = gpu
        self._reader = None

    @property
    def reader(self):
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return self._reader

    def detect_plates(self, roi):
        results = self.reader.readtext(roi)
        plates = []
        for bbox, text, conf in results:
            if conf < 0.3:
                continue
            cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
            if len(cleaned) < 3:
                continue
            x_coords = [int(p[0]) for p in bbox]
            y_coords = [int(p[1]) for p in bbox]
            plates.append({
                "bbox": (min(x_coords), min(y_coords), max(x_coords), max(y_coords)),
                "plate_number": cleaned,
                "confidence": float(conf),
            })
        return plates


class LicensePlateDatabase:
    """Watchlisted plates from an injected loader, refreshed every `cache_ttl` seconds."""

    def __init__(self, loader: Optional[Callable[[], Set[str]]] = None, cache_ttl: float = 60.0):
        self.loader = loader or (lambda: set())
        self.cache_ttl = cache_ttl
        self._cached = None
        self._loaded_at = 0.0

    def _load_watchlist(self):
        if self._cached is None or time.time() - self._loaded_at > self.cache_ttl:
            self._cached = self.loader()
            self._loaded_at = time.time()
        return self._cached

    def is_watchlisted(self, plate_number: str) -> bool:
        return plate_number.upper() in self._load_watchlist()

    def invalidate_cache(self):
        self._cached = None
