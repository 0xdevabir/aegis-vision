"""Alert-worthy identities, kept current from the database while cameras run."""

import logging
import threading
import time

logger = logging.getLogger("HumanAnalysis")

_CACHE: dict = {}
_LOCK = threading.Lock()


def live_criminal_names(static: set, loader, interval: float = 30.0) -> set:
    """One shared set of identities that raise criminal alerts, refreshed in place.

    Faces enrolled (or re-classified) in the dashboard reach every running camera within
    `interval` seconds. Previously the set was read once at startup, so a newly enrolled
    criminal was recognised but never alerted on until the pipeline restarted.
    `static` (config.yaml names) are permanent; a failed refresh keeps the last good list.
    """
    key = tuple(sorted(static))
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
        names = set(static)
        try:
            names |= loader()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to fetch criminal names from DB: {e}")

        def refresh():
            while True:
                time.sleep(interval)
                try:
                    fresh = set(static) | loader()
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Watchlist refresh failed: {e}")
                    continue
                names.update(fresh)
                names.intersection_update(fresh)

        threading.Thread(target=refresh, name="watchlist-refresh", daemon=True).start()
        _CACHE[key] = names
        return names
