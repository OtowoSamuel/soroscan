"""Circuit breaker for external Soroban RPC and Horizon API calls."""
from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, TypeVar

from django.conf import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when a circuit is open and calls are being rejected."""

    def __init__(self, name: str):
        super().__init__(f"Circuit breaker '{name}' is open")
        self.name = name


class CircuitBreaker:
    """Simple thread-safe circuit breaker with closed/open/half-open states."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def _maybe_transition_to_half_open(self) -> None:
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return
        if time.monotonic() - self._opened_at >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
            self._record_state_metric()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._failure_count = 0
        self._record_state_metric()
        self._record_trip_metric()

    def _record_state_metric(self) -> None:
        try:
            from soroscan.ingest import metrics as m

            value = {
                CircuitState.CLOSED: 0,
                CircuitState.HALF_OPEN: 1,
                CircuitState.OPEN: 2,
            }[self._state]
            m.circuit_breaker_state_gauge.labels(name=self.name).set(value)
        except Exception:
            logger.debug("Unable to record circuit breaker state metric", exc_info=True)

    def _record_trip_metric(self) -> None:
        try:
            from soroscan.ingest import metrics as m

            m.circuit_breaker_trips_total.labels(name=self.name).inc()
        except Exception:
            logger.debug("Unable to record circuit breaker trip metric", exc_info=True)

    def _record_call_metric(self, outcome: str) -> None:
        try:
            from soroscan.ingest import metrics as m

            m.circuit_breaker_calls_total.labels(name=self.name, outcome=outcome).inc()
        except Exception:
            logger.debug("Unable to record circuit breaker call metric", exc_info=True)

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.OPEN:
                self._record_call_metric("rejected")
                raise CircuitBreakerOpen(self.name)
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    self._record_call_metric("rejected")
                    raise CircuitBreakerOpen(self.name)
                self._half_open_calls += 1

        try:
            result = func(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failure_count += 1
                if self._state == CircuitState.HALF_OPEN:
                    self._trip()
                elif self._failure_count >= self.failure_threshold:
                    self._trip()
                self._record_call_metric("failure")
            raise

        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._opened_at = None
                self._record_state_metric()
            self._record_call_metric("success")

        return result


_registry_lock = threading.Lock()
_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str) -> CircuitBreaker:
    with _registry_lock:
        breaker = _breakers.get(name)
        if breaker is None:
            breaker = CircuitBreaker(
                name,
                failure_threshold=int(
                    getattr(settings, "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5)
                ),
                recovery_timeout=float(
                    getattr(settings, "CIRCUIT_BREAKER_RECOVERY_TIMEOUT", 30.0)
                ),
            )
            breaker._record_state_metric()
            _breakers[name] = breaker
        return breaker


def execute_with_circuit_breaker(
    name: str,
    func: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    return get_circuit_breaker(name).call(func, *args, **kwargs)
