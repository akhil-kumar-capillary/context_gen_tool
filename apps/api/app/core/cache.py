"""In-memory TTL cache for frequently accessed data.

Avoids repeated DB queries for data that changes infrequently.
No Redis required — suitable for single-instance deployment.

Usage:
    from app.core.cache import app_cache

    # Cache a value with 5-minute TTL
    app_cache.set("user_perms:42", permissions, ttl=300)

    # Get from cache (returns None on miss)
    cached = app_cache.get("user_perms:42")
"""
import time
import logging
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

# Max 1000 entries, default 5-minute TTL
_DEFAULT_TTL = 300
_MAX_SIZE = 1000


class TTLCache:
    """Thread-safe in-memory cache with per-key TTL."""

    def __init__(self, max_size: int = _MAX_SIZE, default_ttl: float = _DEFAULT_TTL):
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expires_at)
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: float | None = None):
        """Cache a value with optional TTL override (seconds)."""
        with self._lock:
            # Evict oldest entries if at capacity
            if len(self._store) >= self._max_size:
                self._evict_expired()
                if len(self._store) >= self._max_size:
                    # Remove oldest entry
                    oldest_key = next(iter(self._store))
                    del self._store[oldest_key]

            expires_at = time.monotonic() + (ttl if ttl is not None else self._default_ttl)
            self._store[key] = (value, expires_at)

    def invalidate(self, key: str):
        """Remove a specific key from the cache."""
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str):
        """Remove all keys starting with prefix."""
        with self._lock:
            keys_to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._store[k]

    def clear(self):
        """Remove all entries."""
        with self._lock:
            self._store.clear()

    def _evict_expired(self):
        """Remove all expired entries (caller must hold lock)."""
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


# Shared application cache
app_cache = TTLCache()
