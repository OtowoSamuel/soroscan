"""Tests for asynchronous SoroScan client."""

import pytest
from pytest_httpx import HTTPXMock

from soroscan import AsyncSoroScanClient
from soroscan.exceptions import SoroScanNotFoundError
from soroscan.models import ContractEvent, TrackedContract


@pytest.mark.asyncio
async def test_async_client_initialization(base_url: str, api_key: str) -> None:
    """Test async client initialization."""
    client = AsyncSoroScanClient(base_url=base_url, api_key=api_key, timeout=60.0)
    assert client.base_url == base_url
    assert client.api_key == api_key
    assert client.timeout == 60.0
    await client.close()


@pytest.mark.asyncio
async def test_async_client_context_manager(base_url: str) -> None:
    """Test async client as context manager."""
    async with AsyncSoroScanClient(base_url=base_url) as client:
        assert client.base_url == base_url


@pytest.mark.asyncio
async def test_async_get_contracts(
    base_url: str,
    sample_contract_data: dict,
    sample_paginated_response: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test async listing contracts."""
    response_data = sample_paginated_response.copy()
    response_data["results"] = [sample_contract_data]

    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/?page=1&page_size=50",
        json=response_data,
    )

    async with AsyncSoroScanClient(base_url=base_url) as client:
        result = await client.get_contracts()

        assert result.count == 100
        assert len(result.results) == 1
        assert isinstance(result.results[0], TrackedContract)
        assert result.results[0].name == "Test Token"


@pytest.mark.asyncio
async def test_async_get_contract(
    base_url: str,
    sample_contract_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test async getting a specific contract."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/1/",
        json=sample_contract_data,
    )

    async with AsyncSoroScanClient(base_url=base_url) as client:
        contract = await client.get_contract("1")

        assert isinstance(contract, TrackedContract)
        assert contract.id == 1
        assert contract.name == "Test Token"


@pytest.mark.asyncio
async def test_async_create_contract(
    base_url: str,
    sample_contract_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test async creating a new contract."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/",
        json=sample_contract_data,
        status_code=201,
    )

    async with AsyncSoroScanClient(base_url=base_url) as client:
        contract = await client.create_contract(
            contract_id="CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
            name="Test Token",
            description="A test token contract",
        )

        assert isinstance(contract, TrackedContract)
        assert contract.name == "Test Token"


@pytest.mark.asyncio
async def test_async_get_events(
    base_url: str,
    sample_event_data: dict,
    sample_paginated_response: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test async querying events."""
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

    async with AsyncSoroScanClient(base_url=base_url) as client:
        result = await client.get_events(
            contract_id="CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
            event_type="transfer",
        )

        assert result.count == 100
        assert len(result.results) == 1
        assert isinstance(result.results[0], ContractEvent)
        assert result.results[0].event_type == "transfer"


@pytest.mark.asyncio
async def test_async_record_event(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test async recording a new event."""
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

    async with AsyncSoroScanClient(base_url=base_url) as client:
        result = await client.record_event(
            contract_id="CCAAA111222333444555666777888999AAABBBCCCDDDEEEFFF",
            event_type="transfer",
            payload_hash="abc123def456",
        )

        assert result.status == "submitted"
        assert result.tx_hash == "tx123456"


@pytest.mark.asyncio
async def test_async_error_handling(
    base_url: str,
    httpx_mock: HTTPXMock,
) -> None:
    """Test async error handling."""
    httpx_mock.add_response(
        url=f"{base_url}/api/contracts/999/",
        json={"detail": "Not found"},
        status_code=404,
    )

    async with AsyncSoroScanClient(base_url=base_url) as client:
        with pytest.raises(SoroScanNotFoundError) as exc_info:
            await client.get_contract("999")

        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_async_concurrent_requests(
    base_url: str,
    sample_contract_data: dict,
    httpx_mock: HTTPXMock,
) -> None:
    """Test concurrent async requests."""
    import asyncio

    # Mock multiple contract responses
    for i in range(1, 4):
        data = sample_contract_data.copy()
        data["id"] = i
        data["name"] = f"Contract {i}"
        httpx_mock.add_response(
            url=f"{base_url}/api/contracts/{i}/",
            json=data,
        )

    async with AsyncSoroScanClient(base_url=base_url) as client:
        # Fetch multiple contracts concurrently
        tasks = [client.get_contract(str(i)) for i in range(1, 4)]
        contracts = await asyncio.gather(*tasks)

        assert len(contracts) == 3
        assert contracts[0].name == "Contract 1"
        assert contracts[1].name == "Contract 2"
        assert contracts[2].name == "Contract 3"
