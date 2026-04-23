"""Tests for synchronous SoroScan client."""

import pytest
from pytest_httpx import HTTPXMock

from soroscan import SoroScanClient
from soroscan.exceptions import (
    SoroScanAuthError,
    SoroScanNotFoundError,
    SoroScanRateLimitError,
    SoroScanValidationError,
)
from soroscan.models import ContractEvent, ContractStats, TrackedContract, WebhookSubscription


def test_client_initialization(base_url: str, api_key: str) -> None:
    """Test client initialization."""
    client = SoroScanClient(base_url=base_url, api_key=api_key, timeout=60.0)
    assert client.base_url == base_url
    assert client.api_key == api_key
    assert client.timeout == 60.0
    client.close()


def test_client_context_manager(base_url: str) -> None:
    """Test client as context manager."""
    with SoroScanClient(base_url=base_url) as client:
        assert client.base_url == base_url


def test_get_contracts(
    base_url: str,
    sample_contract_data: dict,
    sample_paginated_response: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test listing contracts."""
    response_data = sample_paginated_response.copy()
    response_data["results"] = [sample_contract_data]

    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/?page=1&page_size=50",
        json=response_data,
    )

    with SoroScanClient(base_url=base_url) as client:
        result = client.get_contracts()

        assert result.count == 100
        assert len(result.results) == 1
        assert isinstance(result.results[0], TrackedContract)
        assert result.results[0].name == "Test Token"


def test_get_contract(
    base_url: str,
    sample_contract_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test getting a specific contract."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/1/",
        json=sample_contract_data,
    )

    with SoroScanClient(base_url=base_url) as client:
        contract = client.get_contract("1")

        assert isinstance(contract, TrackedContract)
        assert contract.id == 1
        assert contract.name == "Test Token"
        assert contract.event_count == 42


def test_create_contract(
    base_url: str,
    sample_contract_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test creating a new contract."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/",
        json=sample_contract_data,
        status_code=201,
    )

    with SoroScanClient(base_url=base_url) as client:
        contract = client.create_contract(
            contract_id="CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
            name="Test Token",
            description="A test token contract",
        )

        assert isinstance(contract, TrackedContract)
        assert contract.name == "Test Token"


def test_update_contract(
    base_url: str,
    sample_contract_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test updating a contract."""
    updated_data = sample_contract_data.copy()
    updated_data["name"] = "Updated Token"

    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/1/",
        json=updated_data,
    )

    with SoroScanClient(base_url=base_url) as client:
        contract = client.update_contract("1", name="Updated Token")

        assert contract.name == "Updated Token"


def test_delete_contract(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test deleting a contract."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/1/",
        status_code=204,
    )

    with SoroScanClient(base_url=base_url) as client:
        client.delete_contract("1")


def test_get_contract_stats(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test getting contract statistics."""
    stats_data = {
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "name": "Test Token",
        "total_events": 100,
        "unique_event_types": 5,
        "latest_ledger": 100000,
        "last_activity": "2026-01-01T12:00:00Z",
    }

    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/1/stats/",
        json=stats_data,
    )

    with SoroScanClient(base_url=base_url) as client:
        stats = client.get_contract_stats("1")

        assert isinstance(stats, ContractStats)
        assert stats.total_events == 100
        assert stats.unique_event_types == 5


def test_get_events(
    base_url: str,
    sample_event_data: dict,
    sample_paginated_response: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test querying events."""
    response_data = sample_paginated_response.copy()
    response_data["results"] = [sample_event_data]

    httpx_mock.add_response(
        url=(
            f"{base_url}/api/events/?page=1&page_size=50&ordering=-timestamp"
            "&contract__contract_id=CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF"
            "&event_type=transfer"
        ),
        json=response_data,
    )

    with SoroScanClient(base_url=base_url) as client:
        result = client.get_events(
            contract_id="CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
            event_type="transfer",
        )

        assert result.count == 100
        assert len(result.results) == 1
        assert isinstance(result.results[0], ContractEvent)
        assert result.results[0].event_type == "transfer"


def test_get_event(
    base_url: str,
    sample_event_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test getting a specific event."""
    httpx_mock.add_response(
        url=f"{base_url}/api/events/1/",
        json=sample_event_data,
    )

    with SoroScanClient(base_url=base_url) as client:
        event = client.get_event(1)

        assert isinstance(event, ContractEvent)
        assert event.id == 1
        assert event.event_type == "transfer"


def test_record_event(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test recording a new event."""
    response_data = {
        "status": "submitted",
        "tx_hash": "tx123456",
        "transaction_status": "pending",
        "error": None,
    }

    httpx_mock.add_response(
        url=f"{base_url}/api/record-event/",
        json=response_data,
        status_code=202,
    )

    with SoroScanClient(base_url=base_url) as client:
        result = client.record_event(
            contract_id="CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
            event_type="transfer",
            payload_hash="abc123def456",
        )

        assert result.status == "submitted"
        assert result.tx_hash == "tx123456"


def test_get_webhooks(
    base_url: str,
    sample_webhook_data: dict,
    sample_paginated_response: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test listing webhooks."""
    response_data = sample_paginated_response.copy()
    response_data["results"] = [sample_webhook_data]

    httpx_mock.add_response(
        url=f"{base_url}/api/webhooks/?page=1&page_size=50",
        json=response_data,
    )

    with SoroScanClient(base_url=base_url) as client:
        result = client.get_webhooks()

        assert result.count == 100
        assert len(result.results) == 1
        assert isinstance(result.results[0], WebhookSubscription)


def test_create_webhook(
    base_url: str,
    sample_webhook_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test creating a webhook."""
    httpx_mock.add_response(
        url=f"{base_url}/api/webhooks/",
        json=sample_webhook_data,
        status_code=201,
    )

    with SoroScanClient(base_url=base_url) as client:
        webhook = client.create_webhook(
            contract_id=1,
            target_url="https://example.com/webhook",
            event_type="transfer",
        )

        assert isinstance(webhook, WebhookSubscription)
        assert webhook.target_url == "https://example.com/webhook"


def test_test_webhook(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test sending a test webhook."""
    httpx_mock.add_response(
        url=f"{base_url}/api/webhooks/1/test/",
        json={"status": "test_webhook_queued"},
    )

    with SoroScanClient(base_url=base_url) as client:
        result = client.test_webhook(1)

        assert result["status"] == "test_webhook_queued"


def test_error_handling_404(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test 404 error handling."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/999/",
        json={"detail": "Not found"},
        status_code=404,
    )

    with SoroScanClient(base_url=base_url) as client:
        with pytest.raises(SoroScanNotFoundError) as exc_info:
            client.get_contract("999")

        assert exc_info.value.status_code == 404


def test_error_handling_401(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test 401 error handling."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/?page=1&page_size=50",
        json={"detail": "Authentication required"},
        status_code=401,
    )

    with SoroScanClient(base_url=base_url) as client:
        with pytest.raises(SoroScanAuthError) as exc_info:
            client.get_contracts()

        assert exc_info.value.status_code == 401


def test_error_handling_429(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test 429 rate limit error handling."""
    httpx_mock.add_response(
        url=f"{base_url}/api/events/?page=1&page_size=50&ordering=-timestamp",
        json={"detail": "Rate limit exceeded"},
        status_code=429,
    )

    with SoroScanClient(base_url=base_url) as client:
        with pytest.raises(SoroScanRateLimitError) as exc_info:
            client.get_events()

        assert exc_info.value.status_code == 429


def test_error_handling_400(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test 400 validation error handling."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/",
        json={"error": "Invalid contract_id"},
        status_code=400,
    )

    with SoroScanClient(base_url=base_url) as client:
        with pytest.raises(SoroScanValidationError) as exc_info:
            client.create_contract(
                contract_id="invalid",
                name="Test",
            )

        assert exc_info.value.status_code == 400


def test_headers_with_api_key(
    base_url: str,
    api_key: str,
) -> None:
    """Test that API key is included in headers."""
    with SoroScanClient(base_url=base_url, api_key=api_key) as client:
        headers = client._get_headers()

        assert headers["Authorization"] == f"Bearer {api_key}"
        assert headers["Content-Type"] == "application/json"


def test_headers_without_api_key(base_url: str) -> None:
    """Test headers without API key."""
    with SoroScanClient(base_url=base_url) as client:
        headers = client._get_headers()

        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"
