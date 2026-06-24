"""Tests for external API circuit breakers (issue #513)."""
import time
from unittest.mock import MagicMock, patch

import pytest

from soroscan.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    execute_with_circuit_breaker,
    get_circuit_breaker,
)


class TestCircuitBreaker:
    def test_opens_after_failure_threshold(self):
        breaker = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60)

        with pytest.raises(RuntimeError):
            breaker.call(self._raise_error)

        with pytest.raises(RuntimeError):
            breaker.call(self._raise_error)

        assert breaker.state == CircuitState.OPEN

    def test_rejects_calls_when_open(self):
        breaker = CircuitBreaker("test-open", failure_threshold=1, recovery_timeout=60)

        with pytest.raises(RuntimeError):
            breaker.call(self._raise_error)

        with pytest.raises(CircuitBreakerOpen):
            breaker.call(lambda: "ok")

    def test_half_open_recovers_after_success(self):
        breaker = CircuitBreaker(
            "test-half-open",
            failure_threshold=1,
            recovery_timeout=0.01,
            half_open_max_calls=1,
        )

        with pytest.raises(RuntimeError):
            breaker.call(self._raise_error)

        time.sleep(0.02)
        assert breaker.call(lambda: "recovered") == "recovered"
        assert breaker.state == CircuitState.CLOSED

    def test_execute_with_circuit_breaker_records_metrics(self):
        breaker = get_circuit_breaker("metrics-test")
        breaker._failure_count = 0
        breaker._state = CircuitState.CLOSED

        with patch("soroscan.ingest.metrics.circuit_breaker_calls_total") as mock_calls:
            mock_labels = MagicMock()
            mock_calls.labels.return_value = mock_labels
            result = execute_with_circuit_breaker("metrics-test", lambda: 42)
            assert result == 42
            mock_calls.labels.assert_called_with(name="metrics-test", outcome="success")
            mock_labels.inc.assert_called_once()

    @staticmethod
    def _raise_error():
        raise RuntimeError("upstream unavailable")
