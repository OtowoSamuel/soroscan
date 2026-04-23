"""
Integration tests for SoroScan SDK.

These tests verify end-to-end workflows using mocked HTTP responses.
"""

import pytest
from pytest_httpx import HTTPXMock

from soroscan import SoroScanClient
from soroscan.models import ContractEvent, TrackedContract


def test_complete_workflow(
    base_url: str,
    sample_contract_data: dict,
    sample_event_data: dict,
    sample_webhook_data: dict,
    sample_paginated_response: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test a complete workflow: create contract, query events, create webhook."""
    # Mock contract creation
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/",
        json=sample_contract_data,
        status_code=201,
    )

    # Mock events query
    events_response = sample_paginated_response.copy()
    events_response["results"] = [sample_event_data]
    httpx_mock.add_response(
        url=(
            f"{base_url}/api/events/?page=1&page_size=50&ordering=-timestamp"
            "&contract__contract_id=CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF"
            "&event_type=transfer"
        ),
        json=events_response,
    )

    # Mock webhook creation
    httpx_mock.add_response(
        url=f"{base_url}/api/webhooks/",
        json=sample_webhook_data,
        status_code=201,
    )

    # Mock stats query
    stats_data = {
        "contract_id": "CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
        "name": "Test Token",
        "total_events": 42,
        "unique_event_types": 3,
        "latest_ledger": 100000,
        "last_activity": "2026-01-01T12:00:00Z",
    }
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/1/stats/",
        json=stats_data,
    )

    with SoroScanClient(base_url=base_url) as client:
        # Step 1: Create contract
        contract = client.create_contract(
            contract_id="CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
            name="Test Token",
            description="A test token",
        )
        assert isinstance(contract, TrackedContract)
        assert contract.name == "Test Token"

        # Step 2: Query events
        events = client.get_events(
            contract_id=contract.contract_id,
            event_type="transfer",
        )
        assert len(events.results) == 1
        assert isinstance(events.results[0], ContractEvent)

        # Step 3: Create webhook
        webhook = client.create_webhook(
            contract_id=contract.id,
            target_url="https://example.com/webhook",
            event_type="transfer",
        )
        assert webhook.target_url == "https://example.com/webhook"

        # Step 4: Get statistics
        stats = client.get_contract_stats(str(contract.id))
        assert stats.total_events == 42
        assert stats.unique_event_types == 3


def test_pagination_workflow(
    base_url: str,
    sample_event_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test paginating through multiple pages of results."""
    # Mock page 1
    page1_response = {
        "count": 150,
        "next": f"{base_url}/api/events/?page=2",
        "previous": None,
        "results": [sample_event_data] * 50,
    }
    httpx_mock.add_response(
        url=f"{base_url}/api/events/?page=1&page_size=50&ordering=-timestamp",
        json=page1_response,
    )

    # Mock page 2
    page2_response = {
        "count": 150,
        "next": f"{base_url}/api/events/?page=3",
        "previous": f"{base_url}/api/events/?page=1",
        "results": [sample_event_data] * 50,
    }
    httpx_mock.add_response(
        url=f"{base_url}/api/events/?page=2&page_size=50&ordering=-timestamp",
        json=page2_response,
    )

    # Mock page 3
    page3_response = {
        "count": 150,
        "next": None,
        "previous": f"{base_url}/api/events/?page=2",
        "results": [sample_event_data] * 50,
    }
    httpx_mock.add_response(
        url=f"{base_url}/api/events/?page=3&page_size=50&ordering=-timestamp",
        json=page3_response,
    )

    with SoroScanClient(base_url=base_url) as client:
        all_events = []
        page = 1

        while True:
            response = client.get_events(page=page, page_size=50)
            all_events.extend(response.results)

            if not response.next:
                break
            page += 1

        assert len(all_events) == 150
        assert page == 3


def test_event_filtering_workflow(
    base_url: str,
    sample_event_data: dict,
    sample_paginated_response: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test complex event filtering."""
    filtered_response = sample_paginated_response.copy()
    filtered_response["count"] = 10
    filtered_response["results"] = [sample_event_data] * 10

    httpx_mock.add_response(
        url=(
            f"{base_url}/api/events/?page=1&page_size=50&ordering=-ledger"
            "&contract__contract_id=CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF"
            "&event_type=transfer&ledger__gte=100000&ledger__lte=200000"
            "&validation_status=passed"
        ),
        json=filtered_response,
    )

    with SoroScanClient(base_url=base_url) as client:
        events = client.get_events(
            contract_id="CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
            event_type="transfer",
            ledger_min=100000,
            ledger_max=200000,
            validation_status="passed",
            ordering="-ledger",
        )

        assert events.count == 10
        assert len(events.results) == 10
        assert all(e.event_type == "transfer" for e in events.results)


def test_webhook_management_workflow(
    base_url: str,
    sample_webhook_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test webhook creation, update, test, and deletion."""
    # Mock webhook creation
    httpx_mock.add_response(
        url=f"{base_url}/api/webhooks/",
        json=sample_webhook_data,
        status_code=201,
    )

    # Mock webhook update
    updated_webhook = sample_webhook_data.copy()
    updated_webhook["is_active"] = False
    httpx_mock.add_response(
        url=f"{base_url}/api/webhooks/1/",
        json=updated_webhook,
    )

    # Mock webhook test
    httpx_mock.add_response(
        url=f"{base_url}/api/webhooks/1/test/",
        json={"status": "test_webhook_queued"},
    )

    # Mock webhook deletion
    httpx_mock.add_response(
        url=f"{base_url}/api/webhooks/1/",
        status_code=204,
    )

    with SoroScanClient(base_url=base_url) as client:
        # Create webhook
        webhook = client.create_webhook(
            contract_id=1,
            target_url="https://example.com/webhook",
            event_type="transfer",
        )
        assert webhook.is_active is True

        # Update webhook
        updated = client.update_webhook(webhook.id, is_active=False)
        assert updated.is_active is False

        # Test webhook
        result = client.test_webhook(webhook.id)
        assert result["status"] == "test_webhook_queued"

        # Delete webhook
        client.delete_webhook(webhook.id)


@pytest.mark.asyncio
async def test_async_concurrent_workflow(
    base_url: str,
    sample_contract_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test concurrent async operations."""
    import asyncio

    from soroscan import AsyncSoroScanClient

    # Mock multiple contract responses
    for i in range(1, 6):
        data = sample_contract_data.copy()
        data["id"] = i
        data["name"] = f"Contract {i}"
        httpx_mock.add_response(
            url=f"{base_url}/api/contracts/{i}/",
            json=data,
        )

    async with AsyncSoroScanClient(base_url=base_url) as client:
        # Fetch 5 contracts concurrently
        tasks = [client.get_contract(str(i)) for i in range(1, 6)]
        contracts = await asyncio.gather(*tasks)

        assert len(contracts) == 5
        assert all(isinstance(c, TrackedContract) for c in contracts)
        assert [c.name for c in contracts] == [f"Contract {i}" for i in range(1, 6)]
