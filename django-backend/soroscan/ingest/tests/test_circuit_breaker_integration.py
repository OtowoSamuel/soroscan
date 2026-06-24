"""Tests for circuit breaker integration with SorobanClient."""
from unittest.mock import MagicMock, patch

import pytest

from soroscan.circuit_breaker import CircuitBreakerOpen
from soroscan.ingest.stellar_client import SorobanClient


@pytest.mark.django_db
def test_get_events_range_uses_soroban_rpc_breaker():
    client = SorobanClient()
    mock_response = MagicMock(events=[])

    with patch("soroscan.ingest.stellar_client.execute_with_circuit_breaker") as mock_exec:
        mock_exec.return_value = mock_response
        result = client.get_events_range("C123", 1, 10)

    assert result == []
    mock_exec.assert_called_once()
    assert mock_exec.call_args.args[0] == "soroban_rpc"


@pytest.mark.django_db
def test_get_events_range_propagates_open_circuit():
    client = SorobanClient()

    with patch(
        "soroscan.ingest.stellar_client.execute_with_circuit_breaker",
        side_effect=CircuitBreakerOpen("soroban_rpc"),
    ):
        with pytest.raises(CircuitBreakerOpen):
            client.get_events_range("C123", 1, 10)
