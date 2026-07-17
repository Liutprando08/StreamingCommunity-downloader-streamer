import threading
from collections import OrderedDict


class SegmentCache:
    def __init__(self, max_size_mb: int = 50):
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._lock = threading.Lock()
        self._max_bytes = max_size_mb * 1024 * 1024
        self._current_bytes = 0

    def get(self, key: str) -> bytes | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def put(self, key: str, value: bytes) -> None:
        with self._lock:
            if key in self._cache:
                self._current_bytes -= len(self._cache[key])
                del self._cache[key]
            while self._current_bytes + len(value) > self._max_bytes and self._cache:
                _, evicted = self._cache.popitem(last=False)
                self._current_bytes -= len(evicted)
            self._cache[key] = value
            self._current_bytes += len(value)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._current_bytes = 0
