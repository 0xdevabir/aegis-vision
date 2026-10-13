import re
import time
from collections import Counter, defaultdict, deque
from typing import Callable, Optional, Set

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_NOT_PLATE = re.compile(r"[^A-Z0-9ঀ-৿]")
MIN_PLATE_LEN, MAX_PLATE_LEN = 4, 12


def normalize_plate(text: str) -> str:
    """Canonical plate text: upper-case Latin, Bengali letters kept, Bengali digits → ASCII,
    everything else (spaces, dashes, OCR noise) dropped. Used for both OCR reads and the
    watchlist, so "ঢাকা মেট্রো-গ ১২-৩৪৫৬" and "ঢাকামেট্রোগ123456" compare equal."""
    return _NOT_PLATE.sub("", (text or "").upper().translate(_BN_DIGITS))


def plausible_plate(plate: str) -> bool:
    """Cheap filter for OCR hits that are not plates (bumper stickers, shop signs)."""
    return MIN_PLATE_LEN <= len(plate) <= MAX_PLATE_LEN and any(c.isdigit() for c in plate)


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
            cleaned = normalize_plate(text)
            if not plausible_plate(cleaned):
                continue
            x_coords = [int(p[0]) for p in bbox]
            y_coords = [int(p[1]) for p in bbox]
            plates.append({
                "bbox": (min(x_coords), min(y_coords), max(x_coords), max(y_coords)),
                "plate_number": cleaned,
                "confidence": float(conf),
            })
        return plates


class PlateVoter:
    """Multi-read plate voting per vehicle track: one OCR read is never trusted on its own.

    A plate is confirmed when the same text was read `min_votes` times in the last
    `window` reads of that vehicle.
    """

    def __init__(self, window: int = 5, min_votes: int = 2):
        self.window = window
        self.min_votes = min_votes
        self._reads = defaultdict(lambda: deque(maxlen=window))

    def add(self, key, plate: Optional[str]) -> None:
        self._reads[key].append(plate)

    def confirmed(self, key) -> Optional[str]:
        reads = [r for r in self._reads.get(key, ()) if r]
        if not reads:
            return None
        plate, n = Counter(reads).most_common(1)[0]
        return plate if n >= self.min_votes else None

    def prune(self, live_keys) -> None:
        for k in [k for k in self._reads if k not in live_keys]:
            del self._reads[k]


class LicensePlateDatabase:
    """Watchlisted plates from an injected loader, refreshed every `cache_ttl` seconds."""

    def __init__(self, loader: Optional[Callable[[], Set[str]]] = None, cache_ttl: float = 60.0):
        self.loader = loader or (lambda: set())
        self.cache_ttl = cache_ttl
        self._cached = None
        self._loaded_at = 0.0

    def _load_watchlist(self):
        if self._cached is None or time.time() - self._loaded_at > self.cache_ttl:
            self._cached = {normalize_plate(p) for p in self.loader()}
            self._loaded_at = time.time()
        return self._cached

    def is_watchlisted(self, plate_number: str) -> bool:
        return normalize_plate(plate_number) in self._load_watchlist()

    def invalidate_cache(self):
        self._cached = None
