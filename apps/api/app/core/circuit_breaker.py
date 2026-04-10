"""Simple circuit breaker for external API calls.

States:
- CLOSED: requests flow normally, failures are counted
- OPEN: requests fail immediately with CircuitOpenError
- HALF_OPEN: one test request allowed; success closes, failure reopens

Usage:
    breaker = CircuitBreaker("capillary", failure_threshold=5, recovery_timeout=30)

    async with breaker:
        resp = await httpx_client.get(...)
"""
import asyncio
import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit is open and requests are being rejected."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' is open. Retry after {retry_after:.0f}s."
        )


class CircuitBreaker:
    """Async-safe circuit breaker with configurable thresholds."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._half_open_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def __aenter__(self):
        async with self._lock:
            # Auto-transition OPEN → HALF_OPEN after recovery timeout
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    if not self._half_open_in_flight:
                        self._state = CircuitState.HALF_OPEN
                        logger.info("Circuit '%s' entering half-open state", self.name)

            if self._state == CircuitState.OPEN:
                retry_after = self.recovery_timeout - (
                    time.monotonic() - self._last_failure_time
                )
                raise CircuitOpenError(self.name, max(retry_after, 0))

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight:
                    # Another test request is already in progress — reject this one
                    raise CircuitOpenError(self.name, 1.0)
                self._half_open_in_flight = True
                logger.info("Circuit '%s' half-open — allowing single test request", self.name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._lock:
            self._half_open_in_flight = False

            if exc_type is None:
                # Success
                self._failure_count = 0
                if self._state == CircuitState.HALF_OPEN:
                    self._success_count += 1
                    if self._success_count >= self.success_threshold:
                        self._state = CircuitState.CLOSED
                        self._success_count = 0
                        logger.info("Circuit '%s' closed (recovered)", self.name)
                else:
                    self._state = CircuitState.CLOSED
            else:
                # Failure
                self._failure_count += 1
                self._success_count = 0
                self._last_failure_time = time.monotonic()

                if self._state == CircuitState.HALF_OPEN:
                    self._state = CircuitState.OPEN
                    logger.warning("Circuit '%s' reopened after half-open failure", self.name)
                elif self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "Circuit '%s' opened after %d failures",
                        self.name,
                        self._failure_count,
                    )
        return False  # Don't suppress the exception


# Shared instances for external services
capillary_breaker = CircuitBreaker("capillary", failure_threshold=5, recovery_timeout=30)
